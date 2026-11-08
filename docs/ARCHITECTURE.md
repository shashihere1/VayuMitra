# VayuMitra architecture

A personal air companion: real edge sensors detect hyperlocal air-quality
changes → the AI PC turns readings into a personalized **Asthma Risk Score
(0-100)** + short-horizon forecast → when risk crosses critical, **all devices
respond at once** (buzzer + LED on the board, full-screen alert + one-tap
navigation on the phone, a flagged zone in the cloud). The phone also runs its
own model so it works offline.

```
        ┌────────────────────── Venue Wi-Fi (LAN) ─────────────────────────┐
  ┌─────┴──────┐  telemetry   ┌──────────── AI PC (Snapdragon X Elite) ─────┴──────────┐
  │  UNO Q     │ ────────────►│  Mosquitto broker (:1883)                              │
  │  BME (I2C) │◄── cmd ──────│        ▲               │                               │
  │  + GP2Y10  │              │        │               ▼                               │
  │  (analog), │              │   Orchestrator (FastAPI + MQTT + asyncio)               │
  │  both MCU +│              │    ├─ features (rates, windows)                         │
  │  buzzer/LED│              │    ├─ risk: QNN/NPU → CPU → heuristic  (ai_pc/ml)       │
  └────────────┘              │    ├─ forecast (Holt) + safe windows                   │
        ┌────────────┐        │    ├─ advisory: Foundry Local(NPU) → template          │
        │  Phone     │ risk/  │    └─ EMERGENCY CASCADE state machine (hero)            │
        │  (Kotlin)  │◄alert──│                              │                          │
        │  dashboard │  ack   │   Streamlit dashboard (:8501)│ zones (P2)               │
        │  on-device │ ──────►│                              ▼                          │
        │  model+nav │        └──────────────────── Cloud AI 100 aggregator (P2)────────┘
        └────────────┘
```

## Happy path

```
GP2Y10 + BME → uno_q/main.py → telemetry/<id>
   → orchestrator features → risk inference → risk/<user>  (phone + dashboard)
   → cascade → if CRITICAL:
        emergency/alert     (phone full-screen)
      + device/<id>/cmd     (buzzer + red LED)
      + cloud zone flag
   → phone/knob emergency/ack → de-escalate → device/<id>/cmd{clear} + LED green
```

## Design principles

1. **Contract first.** The only cross-lane coupling is `packages/contract/` +
   `docs/MQTT_CONTRACT.md`. No lane imports another lane's code.
2. **One local MQTT broker** (Mosquitto on the AI PC). No internet in the core
   loop → "runs on the edge".
3. **Real sensing, software fallbacks.** Sensors are real hardware. Every
   *software* optional degrades cleanly: NPU→CPU→heuristic, on-device
   LLM→template, cloud→template. The system never crashes; a demo spike injector
   is kept as backup.
4. **Instrumented latency** at every hop, shown on the dashboard HUD.

## The hero: emergency cascade

Per-user state machine `NORMAL → WATCH → EMERGENCY → ACKED` with **hysteresis +
dwell** (`ai_pc/orchestrator/cascade.py`). One event → four coordinated device
behaviors, a shared `alert_id` + timestamps, an ack loop with 20 s re-alerts,
and measured cross-device latency. Pure + clock-injected, so it is
deterministically unit-tested (`tests/test_cascade.py`).

| From | Event | To | Actions |
|---|---|---|---|
| NORMAL | score ≥ warning ×2 | WATCH | LED amber |
| WATCH | score ≥ critical ×2 | EMERGENCY | fire cascade (alert + alarm + red) |
| WATCH | score < warning ×3 | NORMAL | LED green |
| EMERGENCY | EmergencyAck | ACKED | buzzer off, LED amber, stop re-alerts |
| EMERGENCY | no ack in 20 s | EMERGENCY | re-publish alert + re-buzz |
| ACKED/EMERGENCY | score < clear ×3 | NORMAL | LED green + DeviceCommand{clear} |

## Degradation matrix

| Optional | Primary | Fallback 1 | Fallback 2 |
|---|---|---|---|
| Risk inference | QNN/NPU (INT8) | onnxruntime CPU (FP32) | Python heuristic |
| Advisory | Foundry Local (NPU) | — | template by level+factor |
| Forecast | statsmodels Holt | builtin Holt | — |
| Cloud | Cloud AI 100 endpoint | — | template outlook |
| Telemetry | real BME + GP2Y10 | `main.py --mock` | orchestrator `--sim` |
| Phone risk | AI-PC risk over MQTT | on-device TFLite (offline) | — |
