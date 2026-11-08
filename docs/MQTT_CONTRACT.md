# VayuMitra MQTT contract

The single cross-lane coupling. All topics are under `vayumitra/`. Every payload
carries `schema_version` (=1), `msg_type`, and `ts` (RFC-3339 UTC). The
authoritative schema is `packages/contract/schema/messages.schema.json`; the
mobile lane mirrors the DTOs below.

## Topics

| Topic | Publisher → Subscriber | Type | QoS | Retained |
|---|---|---|---|---|
| `vayumitra/telemetry/{device_id}` | UNO Q → orchestrator, dashboard | SensorReading | 1 | no |
| `vayumitra/status/{device_id}` | any → all (LWT) | DeviceStatus | 1 | yes |
| `vayumitra/profile/{user_id}` | phone → orchestrator | Profile | 1 | yes |
| `vayumitra/risk/{user_id}` | orchestrator → phone, dashboard | RiskAssessment | 1 | yes |
| `vayumitra/forecast/{user_id}` | orchestrator → phone, dashboard | ForecastUpdate | 1 | no |
| `vayumitra/emergency/alert` | orchestrator → phone, dashboard, cloud | EmergencyAlert | 1 | no |
| `vayumitra/emergency/ack` | phone/knob → orchestrator | EmergencyAck | 1 | no |
| `vayumitra/device/{device_id}/cmd` | orchestrator → UNO Q | DeviceCommand | 1 | no |
| `vayumitra/cloud/zones` | cloud → phone, dashboard | CloudZoneUpdate | 1 | yes |

## Example payloads

### SensorReading — `telemetry/unoq-01`
```json
{
  "schema_version": 1, "msg_type": "SensorReading",
  "ts": "2026-07-10T12:00:00.000Z", "device_id": "unoq-01",
  "pm1_0": null, "pm25": 42.0, "pm10": null,
  "temperature": 28.4, "humidity": 55.1, "pressure": 1008.2,
  "voc_index": 63.0, "source": "bme680+gp2y10"
}
```
> `pm10`/`pm1_0` are null (GP2Y10 gives one value); the orchestrator derives
> `pm10 ≈ pm25 × 1.4` when needed.

### Profile — `profile/demo-user` (retained)
```json
{
  "schema_version": 1, "msg_type": "Profile",
  "ts": "2026-07-10T11:59:00.000Z", "user_id": "demo-user",
  "severity": "severe", "triggers": ["smoke", "humidity", "voc"],
  "aqi_tolerance": 80, "humidity_threshold": 65, "medication": "albuterol"
}
```

### RiskAssessment — `risk/demo-user` (retained)
```json
{
  "schema_version": 1, "msg_type": "RiskAssessment",
  "ts": "2026-07-10T12:00:01.000Z", "user_id": "demo-user", "device_id": "unoq-01",
  "risk_score": 88.5, "risk_level": "critical",
  "engine": "npu", "inference_ms": 0.42,
  "top_factors": ["high PM2.5", "rapid PM2.5 rise", "elevated VOC / gas"],
  "advisory": "Air quality is hazardous now - move indoors and keep your inhaler ready.",
  "advisory_source": "llm"
}
```
`risk_level`: `<25 low, <50 moderate, <75 high, ≥75 critical`.
`engine`: `npu | cpu | heuristic`. `advisory_source`: `llm | template`.

### ForecastUpdate — `forecast/demo-user`
```json
{
  "schema_version": 1, "msg_type": "ForecastUpdate",
  "ts": "2026-07-10T12:00:30.000Z", "user_id": "demo-user", "horizon_min": 30,
  "predictions": { "pm25": [45.1, 52.0, 61.3], "humidity": [56.0, 58.2, 60.1] },
  "threshold_breach_min": 12,
  "safe_windows": [ { "start_min": 20, "end_min": 30 } ]
}
```

### EmergencyAlert — `emergency/alert`
```json
{
  "schema_version": 1, "msg_type": "EmergencyAlert",
  "ts": "2026-07-10T12:00:02.000Z", "alert_id": "demo-user-alert-1",
  "user_id": "demo-user", "risk_score": 91.0,
  "reason": "high PM2.5", "recommended_action": "Move to clean air and keep your reliever inhaler ready.",
  "safe_zone": { "name": "Shivaji Park (open ground)", "lat": 19.0281, "lon": 72.8397, "distance_m": 640.2 }
}
```

### EmergencyAck — `emergency/ack`
```json
{
  "schema_version": 1, "msg_type": "EmergencyAck",
  "ts": "2026-07-10T12:00:07.000Z", "alert_id": "demo-user-alert-1",
  "user_id": "demo-user", "source": "mobile"
}
```
`source`: `mobile | knob`.

### DeviceCommand — `device/unoq-01/cmd`
```json
{
  "schema_version": 1, "msg_type": "DeviceCommand",
  "ts": "2026-07-10T12:00:02.000Z",
  "action": "alarm_on", "led_color": "red", "alert_id": "demo-user-alert-1"
}
```
`action`: `alarm_on | alarm_off | led | clear`. `led_color`: `green | amber | red | off`.

### DeviceStatus — `status/unoq-01` (retained, also the LWT)
```json
{
  "schema_version": 1, "msg_type": "DeviceStatus",
  "ts": "2026-07-10T11:58:00.000Z", "device_id": "unoq-01",
  "online": true, "role": "uno_q"
}
```
`role`: `uno_q | mobile | ai_pc | cloud`.

### CloudZoneUpdate — `cloud/zones` (retained)
```json
{
  "schema_version": 1, "msg_type": "CloudZoneUpdate",
  "ts": "2026-07-10T12:00:00.000Z",
  "zones": [ { "name": "Zone 1 (19.06,72.88)", "lat": 19.06, "lon": 72.88, "aqi": 160, "level": "critical" } ],
  "outlook_48h": "48h outlook: air quality worsening; peak zone AQI ~160.",
  "source": "template"
}
```
`source`: `cloud_ai_100 | template`.

## Feature vector (`FEATURE_ORDER`)

Shared by `orchestrator/features.py` and `ai_pc/ml`:
```
[ pm25, pm10, temperature, humidity, voc_index, pressure,
  pm25_rate_per_min, humidity_rate_per_min, temp_rate_per_min,
  severity_ordinal, personal_sensitivity ]
```
