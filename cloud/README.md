# Cloud aggregator (P2 — future work)

Buckets device/alert locations into city-wide **zones** and publishes a retained
`CloudZoneUpdate` on `vayumitra/cloud/zones` with a 24-48 h outlook. The
dashboard and phone can render these hotspots.

## Run (locally, for the demo)

```bash
pip install paho-mqtt python-dotenv
python -m cloud.aggregator
```

It seeds a small synthetic fleet around `DEVICE_LAT/LON` so the map is populated,
and flags the device's own zone when it ingests an `EmergencyAlert`.

## How it *would* deploy on Cloud AI 100

Set `CLOUD_AI_ENDPOINT` to a Qualcomm **Cloud AI 100 / Cirrascale** inference
endpoint; the aggregator would POST fleet features there for a real 24-48 h
outlook. Without it, a deterministic **template** outlook is used
(`source: "template"`) so the offline path always works.

## Files
- `aggregator.py` — MQTT subscriber + zone publisher
- `zones.py` — geo-bucketing (`aggregate`) + `haversine_m`
