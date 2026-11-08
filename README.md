# VayuMitra 🌬️

**A personal air companion for asthma care — edge AI across four devices.**

Real edge sensors detect hyperlocal air-quality changes → an AI PC turns
readings into a personalized **Asthma Risk Score (0-100)** + short-horizon
forecast → when risk crosses critical, **all devices respond at once**: a buzzer
+ red LED on the board, a full-screen alert with one-tap navigation on the
phone, and a flagged zone in the cloud. The phone also runs its own model, so it
works offline.

Built for the **Qualcomm Snapdragon Multiverse Hackathon** (30-hour build).

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full diagram and the
degradation matrix. The hero is the **emergency cascade** — one event drives
four coordinated device behaviors over a shared MQTT contract with hysteresis,
an ack loop, and measured cross-device latency.

```
UNO Q (BME680/690 + GP2Y1010, buzzer/LED)  ──telemetry──►  AI PC (Snapdragon X Elite)
        ▲                                                     ├─ Mosquitto broker
        └────────────── cmd ──────────────────────────────── ├─ Orchestrator (risk NPU→CPU→heuristic, cascade)
Phone (Kotlin/Compose, on-device model)  ◄─risk/alert─ ack ─►├─ Streamlit dashboard
                                                              └─ Cloud aggregator (P2)
```

## Developers

| Name | Email |
|---|---|
| VayuMitra Team | pramod.magadum@infosys.com |

*(add teammates here before submission)*

## Setup from scratch

Requirements: **Python 3.11+**, **Mosquitto**, **JDK 17 + Android Studio** (for
the phone), **Arduino App Lab** (for the UNO Q), and — for the full NPU/LLM
demo — **`onnxruntime-qnn`** and **Foundry Local** on the Snapdragon Surface.
For the GP2Y1010 you also need the external parts: a **150 Ω resistor**, a
**220 µF capacitor**, and a **Vo resistor divider** (see
[`uno_q/README.md`](uno_q/README.md)).

```powershell
# 1. clone, then from the repo root:
./infra/scripts/setup.ps1
#    -> creates .venv, installs ai_pc/requirements.txt + the contract, seeds .env

# 2. install the broker
winget install EclipseFoundation.Mosquitto

# 3. (Snapdragon Surface, for the NPU + LLM demo)
.\.venv\Scripts\python -m pip install onnxruntime-qnn
winget install Microsoft.FoundryLocal
.\.venv\Scripts\python -m pip install foundry-local-sdk-winml openai

# 4. set MQTT_HOST in .env to this PC's LAN IP (run: ipconfig)
```

## Run & usage

```powershell
# Full stack (broker + orchestrator + dashboard). -Sim = no peripherals (demo insurance).
./infra/scripts/run_all.ps1 -Sim      # or without -Sim for real devices
# -> dashboard http://localhost:8501 , API http://localhost:8000/state

# UNO Q: create the App Lab app (see uno_q/README.md), set MQTT_HOST, flash + run.
#        Laptop fallback (no board):
.\.venv\Scripts\python uno_q\python\main.py --mock

# Phone: open mobile/ in Android Studio, Run with -PMQTT_HOST=<LAN IP>.

# Stop everything:
./infra/scripts/stop_all.ps1
```

The script prints the **LAN IP** to enter as `MQTT_HOST` on the phone and UNO Q.

### ML pipeline (P1)

```powershell
.\.venv\Scripts\python -m ai_pc.ml.gen_data       # synthetic labels via heuristic
.\.venv\Scripts\python -m ai_pc.ml.train_risk     # -> models/risk_fp32.onnx (needs torch, onnx)
.\.venv\Scripts\python -m ai_pc.ml.quantize       # RUN ON x64 -> models/risk_int8.onnx (commit it)
.\.venv\Scripts\python -m ai_pc.ml.verify_npu     # on the Surface -> QNNExecutionProvider
.\.venv\Scripts\python -m ai_pc.ml.benchmark      # -> ai_pc/ml/benchmark.md (NPU vs CPU)
```

## Testing

```powershell
.\.venv\Scripts\python -m pytest -q
```
Covers the contract (valid/invalid per type), the heuristic (bounded, monotonic,
severity ordering, spike), the cascade (dwell, ack, hysteresis, clear — fake
clock), and an end-to-end smoke test (reading → risk; spike → emergency alert →
ack clears it).

## License

**MIT** — see [`LICENSE`](LICENSE). The majority of the system runs on the edge
(microcontroller + AI PC + phone); the cloud aggregator is optional (P2).

## Notes & honesty

- **Training data is synthetic** — sampled across realistic ranges and labeled
  by the documented `heuristic()`. At inference the model runs on **real** BME +
  GP2Y1010 readings, and the same heuristic is the runtime fallback + explainer.
- **GP2Y1010AU0F is a *relative* dust proxy** (one crude value, needs per-unit
  calibration); `pm10`/`pm1_0` are published null and `pm10 ≈ pm25 × 1.4` is
  derived. It's a smoke-detector part → great, fast demo spike.
- **BME680 vs BME690:** BME680 uses `Adafruit_BME680`; BME690 uses Bosch
  `BME690_SensorAPI` / BSEC 3.x (wiring identical).
- **Foundry Local is preview (no SLA)** — advisories fall back to templates on
  any error.
- Everything degrades gracefully: NPU→CPU→heuristic, LLM→template,
  cloud→template, hardware→`--mock`/`--sim`, phone→on-device model offline.

## References

- Arduino UNO Q + App Lab — https://docs.arduino.cc/
- Bosch BME680 / BME690 + BSEC — https://www.bosch-sensortec.com/
- Sharp GP2Y1010AU0F datasheet — optical dust sensor
- ONNX Runtime QNN (Hexagon NPU) — https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html
- Microsoft Foundry Local — https://learn.microsoft.com/azure/ai-foundry/foundry-local/
- HiveMQ MQTT Client — https://github.com/hivemq/hivemq-mqtt-client
- LiteRT / TensorFlow Lite — https://ai.google.dev/edge/litert

## Repo layout

```
vayumitra/
├── packages/contract/     # THE only cross-lane coupling (topics, models, schema, validate)
├── ai_pc/
│   ├── broker/            # mosquitto.conf + README
│   ├── orchestrator/      # MQTT + features + inference + forecast + advisory + cascade + API
│   ├── ml/                # heuristic, gen_data, train, quantize, verify_npu, benchmark
│   └── dashboard/         # Streamlit app
├── uno_q/                 # sketch.ino (MCU) + python/main.py (MPU) + mock_hw.py
├── mobile/                # Kotlin + Jetpack Compose Android app
├── cloud/                 # aggregator + zones (P2)
├── infra/scripts/         # setup.ps1 / run_all.ps1 / stop_all.ps1
├── tests/                 # contract / heuristic / cascade / smoke_e2e
└── docs/                  # ARCHITECTURE / MQTT_CONTRACT / DEMO_SCRIPT
```
