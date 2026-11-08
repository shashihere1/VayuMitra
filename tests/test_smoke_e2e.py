"""End-to-end smoke test of the orchestrator pipeline WITHOUT a broker.

We swap the MQTT client for a recorder and drive readings through
``process_reading`` directly:
  * a normal reading yields a published ``RiskAssessment``;
  * a sustained spike drives the cascade to publish an ``EmergencyAlert``.
"""
from __future__ import annotations

import asyncio

from vayumitra_contract import topics
from vayumitra_contract.validate import validate

from ai_pc.orchestrator.config import CFG


class FakeMqtt:
    def __init__(self):
        self.published = []            # list of (topic, payload)

        class _Ev:
            def is_set(self_inner):
                return True
        self.connected = _Ev()

    def publish(self, topic, payload, qos=1, retain=False):
        self.published.append((topic, payload))

    def start(self):
        pass

    def stop(self):
        pass

    def by_type(self, msg_type):
        return [p for _, p in self.published if p.get("msg_type") == msg_type]


def _make_orch():
    CFG.force_no_npu = True
    CFG.force_no_foundry = True
    CFG.sim = False
    from ai_pc.orchestrator.main import Orchestrator
    orch = Orchestrator()
    orch.mqtt = FakeMqtt()
    return orch


def test_reading_produces_risk_assessment():
    orch = _make_orch()

    async def run():
        reading = {
            "schema_version": 1, "msg_type": "SensorReading",
            "ts": "2026-07-10T00:00:00Z", "device_id": CFG.device_id,
            "pm25": 20.0, "pm10": None, "pm1_0": None,
            "temperature": 27.0, "humidity": 52.0, "pressure": 1008.0,
            "voc_index": 40.0, "source": "sim",
        }
        await orch.process_reading(reading)

    asyncio.run(run())
    risks = orch.mqtt.by_type("RiskAssessment")
    assert risks, "no RiskAssessment published"
    validate(risks[-1], "RiskAssessment")
    assert risks[-1]["risk_level"] in ("low", "moderate", "high", "critical")


def test_spike_produces_emergency_alert():
    orch = _make_orch()

    async def run():
        for i in range(6):
            reading = {
                "schema_version": 1, "msg_type": "SensorReading",
                "ts": f"2026-07-10T00:00:0{i}Z", "device_id": CFG.device_id,
                "pm25": 380.0, "pm10": None, "pm1_0": None,
                "temperature": 24.0, "humidity": 82.0, "pressure": 1004.0,
                "voc_index": 480.0, "source": "sim",
            }
            await orch.process_reading(reading)

    asyncio.run(run())
    alerts = orch.mqtt.by_type("EmergencyAlert")
    assert alerts, "spike did not fire an EmergencyAlert"
    validate(alerts[-1], "EmergencyAlert")
    assert alerts[-1]["risk_score"] >= 75

    # a DeviceCommand{alarm_on} + red LED must accompany the fire
    cmds = orch.mqtt.by_type("DeviceCommand")
    assert any(c["action"] == "alarm_on" for c in cmds)
    assert any(c.get("led_color") == "red" for c in cmds)


def test_ack_clears_cascade():
    orch = _make_orch()

    async def run():
        for i in range(6):
            await orch.process_reading({
                "schema_version": 1, "msg_type": "SensorReading",
                "ts": f"2026-07-10T00:00:0{i}Z", "device_id": CFG.device_id,
                "pm25": 380.0, "temperature": 24.0, "humidity": 82.0,
                "pressure": 1004.0, "voc_index": 480.0, "source": "sim",
            })
        alerts = orch.mqtt.by_type("EmergencyAlert")
        alert_id = alerts[-1]["alert_id"]
        await orch._handle_ack({"msg_type": "EmergencyAck", "alert_id": alert_id,
                                "source": "mobile", "user_id": CFG.user_id})

    asyncio.run(run())
    cmds = orch.mqtt.by_type("DeviceCommand")
    assert any(c["action"] == "alarm_off" for c in cmds), "ack did not silence the alarm"
