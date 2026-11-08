"""UNO Q — MPU publisher (Linux side).  **Brains/network only: no sensor I/O.**

Pulls all sensor values from the **Bridge** (the MCU sketch does the real
sensing over I2C + analog), assembles one ``SensorReading`` and publishes it to
``telemetry/<DEVICE_ID>`` sub-minute.  Subscribes to ``device/<id>/cmd`` and
calls the Bridge to drive the buzzer + LED.  Publishes a retained
``DeviceStatus`` and sets an MQTT LWT.

Runs on hardware inside an Arduino App Lab app, **and** on any laptop with
``--mock`` (the mock stands in for the Bridge), which is the guaranteed demo
fallback:

    python uno_q/python/main.py --mock
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

# Windows legacy consoles default to cp1252; the mock prints emoji for
# buzzer/LED actions, so make stdout tolerant to avoid a crash on actuation.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("uno_q")

# --- config from env (mirrors .env) ------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEVICE_ID = os.getenv("DEVICE_ID", "unoq-01")
BME_VARIANT = os.getenv("BME_VARIANT", "bme680")
PUBLISH_INTERVAL_S = 2.0
PREFIX = "vayumitra"

# Optional: use the shared contract if it's installed (validation + builders).
try:
    from vayumitra_contract import models as _models
    from vayumitra_contract import topics as _topics
    _HAVE_CONTRACT = True
except Exception:
    _HAVE_CONTRACT = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def t_telemetry(did): return _topics.telemetry(did) if _HAVE_CONTRACT else f"{PREFIX}/telemetry/{did}"
def t_status(did): return _topics.status(did) if _HAVE_CONTRACT else f"{PREFIX}/status/{did}"
def t_cmd(did): return _topics.device_cmd(did) if _HAVE_CONTRACT else f"{PREFIX}/device/{did}/cmd"
def t_alert(): return _topics.emergency_alert() if _HAVE_CONTRACT else f"{PREFIX}/emergency/alert"
def t_ack(): return _topics.emergency_ack() if _HAVE_CONTRACT else f"{PREFIX}/emergency/ack"


def build_reading(sensors: dict) -> dict:
    source = f"{BME_VARIANT}+gp2y10"
    if _HAVE_CONTRACT:
        return _models.SensorReading(
            device_id=DEVICE_ID,
            pm25=float(sensors.get("pm25", 0.0)),
            pm10=None, pm1_0=None,
            temperature=float(sensors.get("temperature", 0.0)),
            humidity=float(sensors.get("humidity", 0.0)),
            pressure=sensors.get("pressure"),
            voc_index=sensors.get("voc_index"),
            source=source,
        ).to_payload()
    return {
        "schema_version": 1, "msg_type": "SensorReading", "ts": _now_iso(),
        "device_id": DEVICE_ID,
        "pm25": float(sensors.get("pm25", 0.0)), "pm10": None, "pm1_0": None,
        "temperature": float(sensors.get("temperature", 0.0)),
        "humidity": float(sensors.get("humidity", 0.0)),
        "pressure": sensors.get("pressure"),
        "voc_index": sensors.get("voc_index"),
        "source": source,
    }


def status_payload(online: bool) -> dict:
    if _HAVE_CONTRACT:
        return _models.DeviceStatus(device_id=DEVICE_ID, online=online, role="uno_q").to_payload()
    return {"schema_version": 1, "msg_type": "DeviceStatus", "ts": _now_iso(),
            "device_id": DEVICE_ID, "online": online, "role": "uno_q"}


def ack_payload(alert_id) -> dict:
    if _HAVE_CONTRACT:
        return _models.EmergencyAck(alert_id=alert_id or "unknown", source="knob",
                                    user_id=os.getenv("USER_ID")).to_payload()
    return {"schema_version": 1, "msg_type": "EmergencyAck", "ts": _now_iso(),
            "alert_id": alert_id or "unknown", "source": "knob",
            "user_id": os.getenv("USER_ID")}


def load_bridge(use_mock: bool):
    """Return a bridge object exposing:
        read_sensors() -> dict(pm25,temperature,humidity,pressure,voc_index)
        set_alarm(bool); set_led(color:str); poll_knob() -> bool
    Falls back to the mock when the real Bridge import fails or --mock is passed.
    """
    if not use_mock:
        try:
            # Real Arduino App Lab Bridge (Python side).  The exact import/API
            # depends on your installed App Lab runtime; adapt to match your
            # Bridge example.  We expect the sketch to have registered the
            # sensor variables + the set_alarm/set_led/knob functions.
            from bridge_hw import RealBridge  # noqa: WPS433 (device-only module)
            log.info("using RealBridge (App Lab)")
            return RealBridge()
        except Exception as e:
            log.warning("real Bridge unavailable (%s) -> falling back to mock", e)
    from mock_hw import MockBridge
    log.info("using MockBridge (synthetic sensors + printed actuation)")
    return MockBridge()


class Publisher:
    def __init__(self, bridge):
        self.bridge = bridge
        self.latest_alert_id = None
        cid = f"vayumitra-unoq-{DEVICE_ID}"
        if hasattr(mqtt, "CallbackAPIVersion"):
            self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
        else:
            self.c = mqtt.Client(client_id=cid)
        self.c.will_set(t_status(DEVICE_ID), json.dumps(status_payload(False)),
                        qos=1, retain=True)
        self.c.on_connect = self._on_connect
        self.c.on_message = self._on_message
        self.c.reconnect_delay_set(1, 30)

    def _on_connect(self, *args):
        log.info("connected to broker %s:%s", MQTT_HOST, MQTT_PORT)
        self.c.subscribe(t_cmd(DEVICE_ID), qos=1)
        self.c.subscribe(t_alert(), qos=1)
        self.c.publish(t_status(DEVICE_ID), json.dumps(status_payload(True)),
                       qos=1, retain=True)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        mt = payload.get("msg_type")
        if mt == "DeviceCommand":
            self._handle_cmd(payload)
        elif mt == "EmergencyAlert":
            self.latest_alert_id = payload.get("alert_id")

    def _handle_cmd(self, cmd: dict):
        action = cmd.get("action")
        if action == "alarm_on":
            self.bridge.set_alarm(True)
        elif action == "alarm_off":
            self.bridge.set_alarm(False)
        elif action == "led":
            self.bridge.set_led(cmd.get("led_color", "off"))
        elif action == "clear":
            self.bridge.set_alarm(False)
            self.bridge.set_led("green")
        log.info("cmd: %s %s", action, cmd.get("led_color", ""))

    def run(self):
        self.c.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.c.loop_start()
        running = {"v": True}

        def _stop(*_):
            running["v"] = False
        signal.signal(signal.SIGINT, _stop)
        try:
            signal.signal(signal.SIGTERM, _stop)
        except (ValueError, AttributeError):
            pass

        try:
            while running["v"]:
                sensors = self.bridge.read_sensors()
                reading = build_reading(sensors)
                self.c.publish(t_telemetry(DEVICE_ID), json.dumps(reading), qos=1)
                log.info("telemetry pm25=%.1f temp=%.1f hum=%.1f voc=%s",
                         reading["pm25"], reading["temperature"],
                         reading["humidity"], reading.get("voc_index"))
                if self.bridge.poll_knob():
                    ack = ack_payload(self.latest_alert_id)
                    self.c.publish(t_ack(), json.dumps(ack), qos=1)
                    log.info("knob pressed -> EmergencyAck(alert_id=%s)", ack["alert_id"])
                time.sleep(PUBLISH_INTERVAL_S)
        finally:
            self.c.publish(t_status(DEVICE_ID), json.dumps(status_payload(False)),
                           qos=1, retain=True)
            self.c.loop_stop()
            self.c.disconnect()
            log.info("publisher stopped")


def main():
    p = argparse.ArgumentParser(description="UNO Q MPU publisher")
    p.add_argument("--mock", action="store_true", help="use the synthetic mock Bridge (laptop)")
    args = p.parse_args()

    bridge = load_bridge(use_mock=args.mock)
    Publisher(bridge).run()


# When packaged as an App Lab app, the runtime calls App.run(); on a laptop we
# just run main().  We support both by running main() here.
if __name__ == "__main__":
    main()
