"""VayuMitra orchestrator — the AI-PC brain.

Async app that:
  * ingests ``SensorReading`` from MQTT (or a built-in simulator with ``--sim``),
  * builds features, runs risk inference (NPU -> CPU -> heuristic),
  * publishes ``RiskAssessment`` + periodic ``ForecastUpdate``,
  * drives the **emergency cascade** state machine and fans its actions out to
    ``EmergencyAlert`` + ``DeviceCommand`` messages,
  * serves a small FastAPI control surface (``/healthz``, ``/state``,
    ``/trigger_spike``).

Run:
    python -m ai_pc.orchestrator.main            # real telemetry from the LAN
    python -m ai_pc.orchestrator.main --sim      # no hardware; built-in spike
    python -m ai_pc.orchestrator.main --no-npu --no-foundry
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import time
from typing import Dict, Optional

from vayumitra_contract import models, topics

from ai_pc.orchestrator import forecast as fc
from ai_pc.orchestrator import safe_zones
from ai_pc.orchestrator.advisory import AdvisoryEngine, template_advisory
from ai_pc.orchestrator.cascade import CascadeManager
from ai_pc.orchestrator.config import CFG
from ai_pc.orchestrator.features import FeatureStore, build_features
from ai_pc.orchestrator.inference import RiskModel
from ai_pc.orchestrator.metrics import METRICS
from ai_pc.orchestrator.mqtt_client import MqttClient
from ai_pc.orchestrator.simulator import Simulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vayumitra.orchestrator")

SIM_INTERVAL_S = 2.0
FORECAST_INTERVAL_S = 30.0
TICK_INTERVAL_S = 1.0
PM25_FORECAST_THRESHOLD = 120.0  # ug/m3-equiv considered unhealthy for the breach calc


class Orchestrator:
    def __init__(self) -> None:
        self.cfg = CFG
        self.feature_store = FeatureStore()
        self.risk_model = RiskModel(use_npu=self.cfg.npu_enabled)
        self.advisor = AdvisoryEngine(self.cfg.foundry_enabled, self.cfg.foundry_model)
        self.cascade = CascadeManager(
            critical=self.cfg.risk_critical,
            warning=self.cfg.risk_warning,
            clear=self.cfg.risk_clear,
        )

        self.profiles: Dict[str, dict] = {}
        self.latest_risk: Dict[str, dict] = {}
        self.latest_reading: Dict[str, dict] = {}

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: "asyncio.Queue[tuple[str, dict]]" = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._sim_device_ids: set[str] = set()

        # simulator is always available (as demo-spike backup, even on hardware)
        self.simulator = Simulator(device_id=self.cfg.device_id, source="sim")
        if self.cfg.sim:
            self._sim_device_ids.add(self.cfg.device_id)

        # MQTT
        lwt = models.DeviceStatus(device_id="ai_pc", online=False, role="ai_pc").to_payload()
        self.mqtt = MqttClient(
            host=self.cfg.mqtt_host,
            port=self.cfg.mqtt_port,
            client_id=f"vayumitra-orchestrator-{self.cfg.device_id}",
            on_message=self._on_mqtt_message,
            subscriptions=[
                topics.all_telemetry(),
                topics.all_profiles(),
                topics.all_status(),
                topics.emergency_ack(),
            ],
            lwt_topic=topics.status("ai_pc"),
            lwt_payload=lwt,
        )

    # --- device/user mapping (single-user demo) --------------------------- #
    def _user_for_device(self, device_id: str) -> str:
        return self.cfg.user_id

    def _device_for_user(self, user_id: str) -> str:
        return self.cfg.device_id

    # --- MQTT plumbing ---------------------------------------------------- #
    def _on_mqtt_message(self, topic: str, payload: dict) -> None:
        """Runs on paho's network thread — hop onto the event loop."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (topic, payload))

    async def _consume(self) -> None:
        while True:
            topic, payload = await self._queue.get()
            try:
                await self._dispatch(topic, payload)
            except Exception:
                log.exception("dispatch failed for %s", topic)

    async def _dispatch(self, topic: str, payload: dict) -> None:
        mt = payload.get("msg_type") or topics.msg_type_for_topic(topic)
        if mt == "SensorReading":
            did = payload.get("device_id", "")
            if did in self._sim_device_ids:
                return  # processed locally in sim mode; avoid double-count
            await self.process_reading(payload)
        elif mt == "Profile":
            uid = payload.get("user_id", topics.user_id_from_topic(topic))
            self.profiles[uid] = payload
            log.info("profile updated for %s: severity=%s tol=%s",
                     uid, payload.get("severity"), payload.get("aqi_tolerance"))
        elif mt == "EmergencyAck":
            await self._handle_ack(payload)
        elif mt == "DeviceStatus":
            log.debug("status: %s", payload)
        # RiskAssessment / DeviceCommand / Forecast are things we publish, ignore.

    # --- core pipeline ---------------------------------------------------- #
    async def process_reading(self, reading: dict) -> None:
        t0 = time.perf_counter()
        now = time.monotonic()
        device_id = reading.get("device_id", self.cfg.device_id)
        user_id = self._user_for_device(device_id)
        profile = self.profiles.get(user_id)

        self.latest_reading[device_id] = reading
        buf = self.feature_store.add_reading(reading)
        feats = build_features(reading, buf, profile)

        score, level, engine, inf_ms, factors = self.risk_model.predict(feats)
        if inf_ms:
            METRICS.record("inference_ms", inf_ms)

        advisory, adv_source = self._make_advisory(reading, level, factors, profile)

        risk = models.RiskAssessment(
            user_id=user_id,
            device_id=device_id,
            risk_score=score,
            risk_level=level,
            engine=engine,
            inference_ms=inf_ms or None,
            top_factors=factors,
            advisory=advisory,
            advisory_source=adv_source,
        ).to_payload()
        self.mqtt.publish(topics.risk(user_id), risk, retain=True)
        self.latest_risk[user_id] = risk
        METRICS.record_since("ingest_to_risk_ms", t0)

        # drive the cascade
        m = self.cascade.machine(user_id)
        reason = factors[0] if factors else "elevated risk"
        actions = m.on_reading(score, now, reason=reason)
        self._run_actions(user_id, device_id, score, actions)

        log.info("risk[%s] %.1f (%s) engine=%s state=%s factors=%s",
                 user_id, score, level, engine, m.state.value, ", ".join(factors))

    def _make_advisory(self, reading, level, factors, profile):
        # Save LLM calls for elevated states; templates are instant + safe.
        if self.cfg.foundry_enabled and level in ("high", "critical"):
            ctx = {
                "pm25": reading.get("pm25"),
                "humidity": reading.get("humidity"),
                "temperature": reading.get("temperature"),
                "voc_index": reading.get("voc_index"),
                "risk_level": level,
                "top_factors": factors,
                "severity": (profile or {}).get("severity", "moderate"),
                "triggers": (profile or {}).get("triggers", []),
            }
            return self.advisor.advise(ctx, level, factors)
        return template_advisory(level, factors), "template"

    def _run_actions(self, user_id, device_id, score, actions) -> None:
        cmd_topic = topics.device_cmd(device_id)
        for a in actions:
            if a.kind == "led":
                self.mqtt.publish(cmd_topic, models.DeviceCommand(
                    action="led", led_color=a.led_color).to_payload())
            elif a.kind == "alarm":
                self.mqtt.publish(cmd_topic, models.DeviceCommand(
                    action="alarm_on" if a.alarm_on else "alarm_off").to_payload())
            elif a.kind == "alert":
                self._fire_alert(user_id, score, a)
            elif a.kind == "clear":
                self.mqtt.publish(cmd_topic, models.DeviceCommand(action="clear").to_payload())
                log.info("cascade CLEARED for %s -> NORMAL", user_id)
            elif a.kind == "ack_latency":
                if a.latency_s is not None:
                    METRICS.record("cascade_to_ack_ms", a.latency_s * 1000.0)
                    log.info("EmergencyAck for %s (cascade->ack %.0f ms)",
                             user_id, a.latency_s * 1000.0)

    def _fire_alert(self, user_id, score, action) -> None:
        zone = safe_zones.nearest(self.cfg.device_lat, self.cfg.device_lon)
        alert = models.EmergencyAlert(
            alert_id=action.alert_id,
            user_id=user_id,
            risk_score=score,
            reason=action.reason or "risk critical",
            recommended_action="Move to clean air and keep your reliever inhaler ready.",
            safe_zone=zone,
        ).to_payload()
        self.mqtt.publish(topics.emergency_alert(), alert)
        tag = "RE-ALERT" if action.is_realert else "FIRE CASCADE"
        log.warning("*** %s *** alert_id=%s score=%.1f zone=%s",
                    tag, action.alert_id, score, zone["name"] if zone else "n/a")

    async def _handle_ack(self, payload: dict) -> None:
        alert_id = payload.get("alert_id")
        source = payload.get("source", "mobile")
        user_id = payload.get("user_id") or self.cfg.user_id
        m = self.cascade.machine(user_id)
        actions = m.on_ack(alert_id, time.monotonic())
        if actions:
            log.info("ack received (source=%s) for alert_id=%s", source, alert_id)
            self._run_actions(user_id, self._device_for_user(user_id), m.last_score, actions)

    # --- periodic loops --------------------------------------------------- #
    async def _sim_loop(self) -> None:
        log.info("simulator loop started (interval=%.1fs)", SIM_INTERVAL_S)
        while True:
            reading = self.simulator.next_reading().to_payload()
            # publish telemetry so the dashboard sees it, then process locally
            self.mqtt.publish(topics.telemetry(reading["device_id"]), reading)
            await self.process_reading(reading)
            await asyncio.sleep(SIM_INTERVAL_S)

    async def _forecast_loop(self) -> None:
        while True:
            await asyncio.sleep(FORECAST_INTERVAL_S)
            for device_id in list(self.latest_reading.keys()):
                buf = self.feature_store.buffer(device_id)
                if buf is None:
                    continue
                user_id = self._user_for_device(device_id)
                data = fc.build_forecast(buf, PM25_FORECAST_THRESHOLD, horizon_min=30)
                payload = models.ForecastUpdate(
                    user_id=user_id,
                    horizon_min=data["horizon_min"],
                    predictions=data["predictions"],
                    threshold_breach_min=data["threshold_breach_min"],
                    safe_windows=data["safe_windows"],
                ).to_payload()
                self.mqtt.publish(topics.forecast(user_id), payload)

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(TICK_INTERVAL_S)
            now = time.monotonic()
            for uid, m in list(self.cascade._machines.items()):
                actions = m.tick(now)
                if actions:
                    self._run_actions(uid, self._device_for_user(uid), m.last_score, actions)

    async def _spike_injector(self, steps: int = 14) -> None:
        """One-shot backup: push a scripted spike through the pipeline."""
        if self.cfg.sim:
            self.simulator.trigger_spike(steps)
            log.warning("demo spike triggered on simulator")
            return
        # hardware mode: inject synthetic spike readings for the demo device
        inj = Simulator(device_id=self.cfg.device_id, source="sim")
        inj.trigger_spike(steps)
        self._sim_device_ids.add(self.cfg.device_id)
        log.warning("demo spike injected (%d readings)", steps + 6)
        try:
            for _ in range(steps + 6):
                r = inj.next_reading().to_payload()
                self.mqtt.publish(topics.telemetry(r["device_id"]), r)
                await self.process_reading(r)
                await asyncio.sleep(SIM_INTERVAL_S)
        finally:
            self._sim_device_ids.discard(self.cfg.device_id)

    # --- lifecycle -------------------------------------------------------- #
    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.mqtt.start()
        self._tasks.append(asyncio.create_task(self._consume(), name="consume"))
        self._tasks.append(asyncio.create_task(self._forecast_loop(), name="forecast"))
        self._tasks.append(asyncio.create_task(self._tick_loop(), name="tick"))
        if self.cfg.sim:
            self._tasks.append(asyncio.create_task(self._sim_loop(), name="sim"))
        log.info("\n%s", self.cfg.banner(self.risk_model.engine,
                                          "foundry" if self.cfg.foundry_enabled else "template"))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self.mqtt.stop()

    # --- API state -------------------------------------------------------- #
    def state_snapshot(self) -> dict:
        return {
            "engine": self.risk_model.engine,
            "advisory_source": "foundry" if self.cfg.foundry_enabled else "template",
            "mqtt_connected": self.mqtt.connected.is_set(),
            "cascades": self.cascade.all_snapshots(),
            "latest_risk": self.latest_risk,
            "latest_reading": self.latest_reading,
            "metrics": METRICS.all(),
            "safe_zones": safe_zones.SAFE_ZONES,
        }


# --------------------------------------------------------------------------- #
def build_api(orch: Orchestrator):
    from fastapi import FastAPI

    app = FastAPI(title="VayuMitra Orchestrator", version="1.0.0")

    @app.get("/healthz")
    def healthz():
        return {
            "status": "ok",
            "engine": orch.risk_model.engine,
            "mqtt_connected": orch.mqtt.connected.is_set(),
        }

    @app.get("/state")
    def state():
        return orch.state_snapshot()

    @app.post("/trigger_spike")
    async def trigger_spike():
        asyncio.create_task(orch._spike_injector())
        return {"triggered": True, "mode": "sim" if orch.cfg.sim else "injector"}

    return app


async def _run(orch: Orchestrator) -> None:
    import uvicorn

    await orch.start()
    app = build_api(orch)
    config = uvicorn.Config(app, host="0.0.0.0", port=orch.cfg.api_port,
                            log_level="warning", loop="asyncio")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await orch.stop()


def main() -> None:
    p = argparse.ArgumentParser(description="VayuMitra orchestrator")
    p.add_argument("--sim", action="store_true", help="run with the built-in simulator (no hardware)")
    p.add_argument("--no-npu", action="store_true", help="force CPU/heuristic (skip NPU)")
    p.add_argument("--no-foundry", action="store_true", help="force template advisories")
    args = p.parse_args()

    CFG.sim = args.sim
    CFG.force_no_npu = args.no_npu
    CFG.force_no_foundry = args.no_foundry

    orch = Orchestrator()
    try:
        asyncio.run(_run(orch))
    except KeyboardInterrupt:
        log.info("shutting down")


if __name__ == "__main__":
    main()
