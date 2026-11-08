"""Cloud aggregator (P2).

Subscribes to ``emergency/alert`` (+ optional telemetry), buckets device/alert
coordinates into geo **zones** (with a small synthetic fleet so the map isn't
empty), and publishes a retained ``CloudZoneUpdate`` on ``cloud/zones`` with a
24-48 h outlook.

If a real Qualcomm **Cloud AI 100 / Cirrascale** endpoint is configured
(``CLOUD_AI_ENDPOINT``), it would be called for the outlook; otherwise a
deterministic **template** forecast is used (``source: "template"``). The whole
thing runs locally for the demo.

Run:
    python -m cloud.aggregator
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from cloud.zones import aggregate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("vayumitra.cloud")

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEVICE_LAT = float(os.getenv("DEVICE_LAT", "19.0760"))
DEVICE_LON = float(os.getenv("DEVICE_LON", "72.8777"))
CLOUD_AI_ENDPOINT = os.getenv("CLOUD_AI_ENDPOINT", "")
PREFIX = "vayumitra"
PUBLISH_INTERVAL_S = 15.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# a small synthetic fleet around the device so the city map is populated
SYNTHETIC_FLEET = [
    {"lat": DEVICE_LAT + 0.03, "lon": DEVICE_LON + 0.02, "aqi": 60},
    {"lat": DEVICE_LAT - 0.04, "lon": DEVICE_LON + 0.05, "aqi": 95},
    {"lat": DEVICE_LAT + 0.06, "lon": DEVICE_LON - 0.03, "aqi": 130},
    {"lat": DEVICE_LAT - 0.02, "lon": DEVICE_LON - 0.06, "aqi": 45},
]


class Aggregator:
    def __init__(self):
        self.lock = threading.Lock()
        # this device's latest observed AQI (from alerts); seed low
        self.device_aqi = 30.0
        cid = "vayumitra-cloud"
        if hasattr(mqtt, "CallbackAPIVersion"):
            self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
        else:
            self.c = mqtt.Client(client_id=cid)
        self.c.on_connect = self._on_connect
        self.c.on_message = self._on_message
        self.c.reconnect_delay_set(1, 30)

    def _on_connect(self, *args):
        log.info("cloud aggregator connected to %s:%s", MQTT_HOST, MQTT_PORT)
        self.c.subscribe(f"{PREFIX}/emergency/alert", qos=1)
        self.c.subscribe(f"{PREFIX}/telemetry/+", qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        mt = payload.get("msg_type")
        with self.lock:
            if mt == "EmergencyAlert":
                # an alert implies a local hotspot
                self.device_aqi = max(self.device_aqi, 160.0)
                log.info("alert ingested -> device zone flagged")
            elif mt == "SensorReading":
                pm25 = float(payload.get("pm25") or 0.0)
                # crude AQI-ish from pm25 proxy
                self.device_aqi = max(30.0, min(300.0, pm25))

    def _outlook(self, zones) -> tuple[str, str]:
        worst = max((z["aqi"] for z in zones), default=0)
        if CLOUD_AI_ENDPOINT:
            # Placeholder for a real Cloud AI 100 call; on failure -> template.
            try:
                # (a real implementation would POST features to the endpoint)
                raise NotImplementedError
            except Exception:
                pass
        trend = "worsening" if worst >= 120 else "stable" if worst >= 60 else "improving"
        text = (f"48h outlook: air quality {trend}; peak zone AQI ~{worst:.0f}. "
                f"Sensitive groups should plan indoor time during peaks.")
        return text, "template"

    def build_update(self) -> dict:
        with self.lock:
            points = list(SYNTHETIC_FLEET) + [
                {"lat": DEVICE_LAT, "lon": DEVICE_LON, "aqi": self.device_aqi}
            ]
        zones = aggregate(points)
        outlook, source = self._outlook(zones)
        return {
            "schema_version": 1, "msg_type": "CloudZoneUpdate", "ts": _now_iso(),
            "zones": zones, "outlook_48h": outlook, "source": source,
        }

    def run(self):
        self.c.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.c.loop_start()
        try:
            while True:
                update = self.build_update()
                self.c.publish(f"{PREFIX}/cloud/zones", json.dumps(update), qos=1, retain=True)
                log.info("published CloudZoneUpdate: %d zones, source=%s",
                         len(update["zones"]), update["source"])
                time.sleep(PUBLISH_INTERVAL_S)
        except KeyboardInterrupt:
            pass
        finally:
            self.c.loop_stop()
            self.c.disconnect()


if __name__ == "__main__":
    Aggregator().run()
