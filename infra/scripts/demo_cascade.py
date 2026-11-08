"""Drive + watch the emergency cascade end-to-end over MQTT (no hardware).

Connects to the broker, subscribes to risk / emergency / device-command topics,
publishes an escalating PM2.5 spike as if it came from the UNO Q, then sends an
EmergencyAck — printing every step so you can see:

    NORMAL -> WATCH -> EMERGENCY -> alert (+ nearest safe zone)
           -> alarm_on + red LED -> ack -> alarm_off

Prereqs (in two other terminals): a broker + the orchestrator running.
    python infra/scripts/demo_cascade.py [--host 127.0.0.1] [--device unoq-01] [--user demo-user]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# Windows legacy consoles default to cp1252 and choke on non-ASCII; make stdout
# tolerant so prints never crash the demo.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PREFIX = "vayumitra"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--device", default="unoq-01")
    ap.add_argument("--user", default="demo-user")
    args = ap.parse_args()

    seen = {"risk": [], "alert": [], "cmd": []}

    if hasattr(mqtt, "CallbackAPIVersion"):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="demo-cascade")
    else:
        c = mqtt.Client(client_id="demo-cascade")

    def on_connect(cl, u, f, rc, p=None):
        cl.subscribe(f"{PREFIX}/risk/+")
        cl.subscribe(f"{PREFIX}/emergency/alert")
        cl.subscribe(f"{PREFIX}/device/+/cmd")

    def on_msg(cl, u, m):
        payload = json.loads(m.payload.decode())
        mt = payload.get("msg_type")
        if mt == "RiskAssessment":
            seen["risk"].append(payload)
            print(f"  risk={payload['risk_score']:>5.1f}  level={payload['risk_level']:<8} "
                  f"engine={payload['engine']}")
        elif mt == "EmergencyAlert":
            seen["alert"].append(payload)
            z = payload.get("safe_zone") or {}
            print(f"  *** EMERGENCY ALERT  id={payload['alert_id']}  score={payload['risk_score']:.1f}  "
                  f"reason='{payload['reason']}'  safe_zone={z.get('name','-')} "
                  f"({z.get('distance_m','?')} m)")
        elif mt == "DeviceCommand":
            seen["cmd"].append(payload)
            print(f"  -> DEVICE CMD: action={payload['action']} led={payload.get('led_color')}")

    c.on_connect = on_connect
    c.on_message = on_msg
    c.connect(args.host, args.port, 30)
    c.loop_start()
    time.sleep(1)

    print(f"\n[1] Publishing an escalating PM2.5 spike to {PREFIX}/telemetry/{args.device} ...\n")
    for i in range(8):
        reading = {
            "schema_version": 1, "msg_type": "SensorReading", "ts": now_iso(),
            "device_id": args.device, "pm25": 380.0, "pm10": None, "pm1_0": None,
            "temperature": 24.0, "humidity": 82.0, "pressure": 1004.0,
            "voc_index": 480.0, "source": "bme680+gp2y10",
        }
        c.publish(f"{PREFIX}/telemetry/{args.device}", json.dumps(reading), qos=1)
        time.sleep(0.8)
    time.sleep(1.5)

    if seen["alert"]:
        alert_id = seen["alert"][-1]["alert_id"]
        print(f"\n[2] Sending EmergencyAck for {alert_id} (simulates the phone 'I'm safe' / knob) ...\n")
        ack = {"schema_version": 1, "msg_type": "EmergencyAck", "ts": now_iso(),
               "alert_id": alert_id, "user_id": args.user, "source": "mobile"}
        c.publish(f"{PREFIX}/emergency/ack", json.dumps(ack), qos=1)
        time.sleep(2)
    else:
        print("\n[2] No EmergencyAlert seen — is the orchestrator running against this broker?\n")

    c.loop_stop()

    cmds = [(x["action"], x.get("led_color")) for x in seen["cmd"]]
    print("\n================= RESULT =================")
    print(f"risk messages   : {len(seen['risk'])}")
    print(f"emergency alerts: {len(seen['alert'])}")
    print(f"device commands : {cmds}")
    ok = (seen["risk"] and seen["alert"]
          and any(a == "alarm_on" for a, _ in cmds)
          and any(led == "red" for _, led in cmds)
          and any(a == "alarm_off" for a, _ in cmds))
    print("CASCADE VERIFIED [PASS]" if ok else "cascade INCOMPLETE [FAIL] (check the orchestrator terminal)")
    print("==========================================")


if __name__ == "__main__":
    main()
