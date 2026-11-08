# vayumitra-contract

The **only** cross-lane coupling in VayuMitra. Six lanes (backend, ML, firmware,
mobile, cloud, dashboard) agree on the wire format through this package plus
[`docs/MQTT_CONTRACT.md`](../../docs/MQTT_CONTRACT.md). No lane imports another
lane's code.

## Install

```bash
pip install -e packages/contract
```

## Use

```python
from vayumitra_contract import topics, models, validate

# build + serialize
reading = models.SensorReading(device_id="unoq-01", pm25=42.0,
                               temperature=28.0, humidity=55.0, source="sim")
payload = reading.to_payload()

# validate against the JSON Schema (source of truth)
validate.validate(payload, "SensorReading")   # raises on bad data

# topics
topics.telemetry("unoq-01")     # -> "vayumitra/telemetry/unoq-01"
topics.risk("demo-user")        # -> "vayumitra/risk/demo-user"
```

## Contents

| File | Purpose |
|---|---|
| `schema/messages.schema.json` | JSON Schema (draft 2020-12), `$defs` per type — **source of truth** |
| `vayumitra_contract/topics.py` | topic builders + wildcard subscriptions |
| `vayumitra_contract/models.py` | pydantic v2 models + `parse()` |
| `vayumitra_contract/validate.py` | `validate()`, `is_valid()`, `iter_errors()` |
