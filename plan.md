# VayuMitra — Build Plan (Real Sensors) for GitHub Copilot

> **What this is:** One ordered spec for GitHub Copilot to generate a **run-ready** codebase for *VayuMitra* — a multi-device edge-AI air-quality + asthma-care system for the **Qualcomm Snapdragon Multiverse Hackathon** (30-hour build).
>
> **This version uses the real sensors we have:** a **Sharp GP2Y1010AU0F** optical dust sensor (analog, used as a PM2.5 proxy) and a **Bosch BME680/BME690** environmental sensor (temperature, humidity, pressure, VOC/gas). Section 2 explains exactly how each sensor is wired and where its data is used across the system.
>
> **How Copilot should use it:** work top-to-bottom, phase by phase; after each phase the repo must run. Where a code snippet is given, match it. Every *software* dependency (NPU, on-device LLM, cloud) must degrade gracefully so the system always runs — but sensing is now real hardware, so those parts are written for real data.

---

## 0. Core principles

1. **Contract first (Hour 0).** The only thing linking the six lanes is `packages/contract/` (JSON Schema) + `docs/MQTT_CONTRACT.md`. No lane imports another lane's code. Build the contract completely before anything else.
2. **One local MQTT broker.** A single **Mosquitto** broker runs on the AI PC. The UNO Q and the phone connect to it over the venue Wi-Fi (LAN). No internet in the core loop = "runs on the edge."
3. **Real sensing, software fallbacks.** Sensors are real. But every *software* optional (NPU→CPU→heuristic, on-device LLM→template, cloud→template) must fall back cleanly and never crash. Keep a "demo spike injector" as backup in case a live spike is slow on stage.
4. **Instrument latency** at every hop and show it on the dashboard.
5. **Runnable + documented + commented.** README must let a stranger run it from scratch.

---

## 1. What we're building & how we win

A "personal air companion": real edge sensors detect hyperlocal air-quality changes → the AI PC turns readings into a personalized **Asthma Risk Score (0–100)** + short-horizon forecast → when risk crosses critical, **all devices respond at once** (buzzer + LED on the board, full-screen alert + one-tap navigation on the phone, a flagged zone in the cloud). The phone also runs its own model so it works offline.

| Criterion | Pts | What earns it here |
|---|---|---|
| **Multi-Device Orchestration** | **100** | The **emergency cascade**: 1 event → 4 coordinated device behaviors, shared contract, hysteresis, ack loop, measured cross-device latency. This is the hero — polish it. |
| Technical Implementation | 40 | Real **NPU inference on the Snapdragon X Elite** (`onnxruntime-qnn`, INT8, HTP burst) + a **CPU-vs-NPU benchmark**; on-device LLM on the NPU; real sub-minute sensing. |
| App Use-Case & Innovation | 25 | Per-user trigger profile; **predictive** warnings ("humidity breaches your threshold in ~25 min"); one-tap clean-air navigation. |
| Deployment & Accessibility | 20 | One command (`run_all.ps1`), clear from-scratch README. |
| Presentation & Documentation | 15 | README, architecture diagram, MQTT contract, commented code, live dashboard, tight demo. |

**Priority tiers (finish P0 before P1, P1 before P2):**
- **P0 (must be flawless):** contract; UNO Q reading BME + GP2Y10 and driving buzzer/LED; orchestrator computing risk (heuristic is fine for P0) + running the cascade; phone showing risk + full-screen emergency + ack; dashboard. **End-to-end cascade on one Wi-Fi.**
- **P1:** trained ONNX model on the NPU + benchmark; on-device model on the phone; Foundry Local advisories; forecasting; latency HUD.
- **P2 (future work per the proposal):** cloud aggregator, 24–48 h outlook, city-wide zones.

---

## 2. Sensors: wiring + where each one is used  ← the important part

**Both sensors are read on the MCU sketch** — the BME over I²C, and the **GP2Y1010AU0F dust sensor over analog + a timed LED pulse** (the analog pin and the microsecond-precise pulse timing both live on the STM32 MCU; Linux is not real-time enough for the pulse). The **MPU `main.py` reads everything from the Bridge and publishes** — it does no direct sensor I/O. (This is simpler than a UART PM sensor: no USB-TTL adapter and no `Serial1`/Bridge conflict.)

### 2.1 Signal → sensor → who reads it → what uses it

| Signal | Sensor | Bus | Read by | Used by (downstream) |
|---|---|---|---|---|
| **PM2.5** (relative dust index) | **GP2Y1010AU0F** | analog + LED-pulse GPIO | `uno_q/sketch/sketch.ino` (ADC) → Bridge | **dominant risk driver**, rate-of-change (spike detection), forecast, cascade trigger, phone + dashboard |
| Temperature (°C) | **BME680/690** | I²C | `sketch.ino` → Bridge | risk (cold-air / rapid temp-drop trigger), UI |
| Humidity (%) | **BME680/690** | I²C | `sketch.ino` → Bridge | risk (humidity-high/low triggers), forecast + breach prediction, UI |
| Pressure (hPa) | **BME680/690** | I²C | `sketch.ino` → Bridge | risk (optional: rapid pressure drop), UI |
| VOC / gas | **BME680/690** | I²C | `sketch.ino` → Bridge | risk (VOC trigger), UI, **great demo spike** (alcohol near sensor) |
| Buzzer (alarm) | Modulino Buzzer | I²C/Qwiic | `sketch.ino` (on command from MPU) | emergency cascade **output** |
| Status LED | UNO Q **onboard RGB LED** | — | `sketch.ino` / MPU | cascade-state indicator (green/amber/red) |
| Physical ack *(optional)* | Modulino Knob button | I²C | `sketch.ino` → Bridge | `EmergencyAck{source:"knob"}` |

*(Modulino Thermo is now redundant — BME covers temp/humidity — so leave it unused or as a backup temp source.)*
*(No PM10/PM1.0 from this sensor — it gives one value. `pm10`/`pm1_0` are published as null; the orchestrator derives `pm10 ≈ pm25×1.4` when it needs it.)*

### 2.2 BME680 / BME690 (I²C) — temperature, humidity, pressure, VOC

- **Wiring:** `VCC→3V3`, `GND→GND`, `SDA→SDA`, `SCL→SCL` (or via the Qwiic connector). I²C address **0x76 or 0x77**. UNO Q I/O is 3.3 V.
- **Read on the MCU sketch.** (The Arduino/Qwiic I²C pins are on the STM32 MCU side, so the sketch reads the BME and **bridges the values to Linux**.)
- **Library:**
  - **BME680** → `Adafruit_BME680` (simple: temperature, humidity, pressure, `gas_resistance` in Ω).
  - **BME690** → Bosch `BME690_SensorAPI` (github.com/boschsensortec/BME690_SensorAPI) or **BSEC 3.x** if you want a calibrated **IAQ** index. `BME690` is a pin-compatible successor to the BME680/688 — wiring is identical.
- **VOC value (recommended simple path, works for both):** read `gas_resistance`; compute a **relative VOC index** against a rolling clean-air baseline — resistance is high in clean air and drops with VOCs:
  ```
  baseline = max gas_resistance seen recently
  voc_index = clamp( 500 * (1 - gas_resistance / baseline), 0, 500 )
  ```
  Optional stretch: use BSEC for a true IAQ/bVOC/CO₂-equivalent output (BSEC 2.x for BME680, BSEC 3.x for BME688/690).
- **Hackathon note:** MOX gas sensors need a burn-in for *absolute* accuracy, so treat VOC as a **trend** value (fine — it's one feature among several). The demo spike (below) works instantly regardless of calibration.

### 2.3 GP2Y1010AU0F (analog optical dust sensor) — PM2.5 proxy

This is a Sharp IR dust sensor with an **analog** output — *not* a digital/UART PM sensor. It gives one crude "dust density" value (no PM2.5/PM10 split), it's noisy, and it isn't truly calibrated to µg/m³, so treat it as a **relative PM2.5 proxy**. It's very responsive to smoke (it's a smoke-detector part), which makes for a strong, fast demo spike.

- **Required external circuit (must build — it won't work without it):**
  - `150 Ω` resistor in series on the **V-LED** pin, with a `220 µF` capacitor from V-LED to GND (reservoir for the pulsed LED current).
  - A **resistor divider on the `Vo` output** to keep it **≤ 3.3 V** (Vo can reach ~3.4–3.6 V and the UNO Q's A0/A1 are **not** 5 V-tolerant). E.g. a ~2:3 divider; record the exact `DUST_DIVIDER` ratio for the conversion.
- **Pinout / wiring (6-pin):** `V-LED`(1)→5 V via 150 Ω (+220 µF to GND) · `LED-GND`(2)→GND · `LED`(3)→a **digital GPIO** (LED pulse control) · `S-GND`(4)→GND · `Vo`(5)→**analog input via the divider** · `Vcc`(6)→5 V. 5 V comes from the UNO Q 5 V pin / USB hub; the LED-control and ADC logic stay ≤ 3.3 V.
- **Read on the MCU sketch** with this timing (the classic GP2Y pulse; `LED` LOW = LED on):
  ```
  every 10 ms:
    digitalWrite(LED_PIN, LOW)          // LED on
    delayMicroseconds(280)              // wait, then sample
    adc = analogRead(DUST_ADC_PIN)
    delayMicroseconds(40)
    digitalWrite(LED_PIN, HIGH)         // LED off (LED on-time ≈ 320 µs)
    // then idle the rest of the 10 ms
  ```
  **Smooth it:** average / median ~100 samples (~1 s) — the raw signal is jittery.
- **Convert to a PM2.5-equivalent (calibrate per unit):**
  ```
  v   = adc/ADC_MAX * VREF * DUST_DIVIDER          // reconstruct Vo in volts
  dust_mg_m3 = max(0, 0.17*v - 0.1)                // common GP2Y approximation
  pm25 = clamp(dust_mg_m3 * 1000, 0, 500)          // µg/m³-equivalent for the model
  ```
  Subtract your measured **clean-air offset** (`Voc`, ~0.6 V) first for a stable zero. Document it as a *relative* index. Publish `pm25`; leave `pm10`/`pm1_0` null.

### 2.4 Reading model (how the two sensors combine into one message)
- **MCU sketch** = *all sensing + actuation*: read BME (I²C) → temperature/humidity/pressure/gas; read GP2Y1010 (pulse + ADC + smoothing) → `pm25`; compute `voc_index`; **bridge all values to Linux**; drive **buzzer + LED** on command; (optional) read Knob button → notify Linux.
- **MPU `main.py`** = *brains + network only*: pull all sensor values from the **Bridge**; assemble one `SensorReading` (`source:"bme680+gp2y10"` or `bme690+gp2y10`); **publish to `telemetry/<device_id>`** over MQTT sub-minute; subscribe to commands and call the Bridge to fire buzzer/LED. **No serial, no direct sensor I/O.**

---

## 3. Architecture

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

**Happy path:** GP2Y10 + BME → `main.py` → `telemetry/<id>` → orchestrator features → risk inference → `risk/<user>` (phone + dashboard) → cascade → if CRITICAL: `emergency/alert` (phone) + `device/<id>/cmd` (buzzer/LED) + cloud flag → phone/knob `emergency/ack` → de-escalate.

---

## 4. Repository layout

```
vayumitra/
├── README.md                 LICENSE (MIT)   .gitignore   .env.example
├── docs/  ARCHITECTURE.md  MQTT_CONTRACT.md  DEMO_SCRIPT.md
├── packages/contract/                 # THE only cross-lane coupling (Lead)
│   ├── pyproject.toml
│   ├── vayumitra_contract/  __init__.py  topics.py  models.py  validate.py
│   └── schema/messages.schema.json
├── ai_pc/
│   ├── broker/       mosquitto.conf   README.md
│   ├── orchestrator/ main.py  mqtt_client.py  features.py  inference.py
│   │                 forecast.py  advisory.py  cascade.py  safe_zones.py
│   │                 simulator.py  metrics.py  config.py
│   ├── ml/           heuristic.py  gen_data.py  train_risk.py  quantize.py
│   │                 verify_npu.py  benchmark.py  models/
│   └── dashboard/    app.py
├── uno_q/                              # Arduino App Lab app (Firmware)
│   ├── app.yaml
│   ├── sketch/  sketch.ino  sketch.yaml      # MCU: BME(I2C)+GP2Y10(analog)+buzzer+LED+knob
│   ├── python/  main.py  mock_hw.py  requirements.txt  # MPU: reads Bridge + MQTT
│   └── README.md
├── mobile/                            # Kotlin + Jetpack Compose (Android)
│   ├── app/  build.gradle.kts  settings.gradle.kts  README.md
├── cloud/  aggregator.py  zones.py  README.md          # P2
├── infra/scripts/  setup.ps1  run_all.ps1  stop_all.ps1
└── tests/  test_contract.py  test_heuristic.py  test_cascade.py  test_smoke_e2e.py
```

---

## 5. Config (`.env.example`)

```
MQTT_HOST=192.168.x.x       # laptop LAN IP (broker). 127.0.0.1 for laptop-only.
MQTT_PORT=1883
DEVICE_ID=unoq-01
USER_ID=demo-user
DEVICE_LAT=19.0760          # for nearest-safe-zone + navigation
DEVICE_LON=72.8777
# --- sensors (all read on the MCU sketch; these constants live in the sketch, mirrored here for docs) ---
BME_VARIANT=bme680          # bme680 | bme690
BME_I2C_ADDR=0x76
DUST_LED_PIN=2              # GP2Y1010 LED-pulse control GPIO
DUST_ADC_PIN=A0            # GP2Y1010 Vo (through the divider), ≤3.3 V
DUST_DIVIDER=1.5           # Vo divider ratio used in the voltage reconstruction
DUST_VOC_OFFSET=0.6        # clean-air Voc (V) — calibrate per unit
# --- software toggles ---
USE_NPU=true                # false forces CPU
USE_FOUNDRY=true            # false forces template advisories
FOUNDRY_MODEL=phi-4-mini
RISK_CRITICAL=75  RISK_WARNING=50  RISK_CLEAR=60   # cascade thresholds (hysteresis)
```
`config.py` loads via `python-dotenv`. Log the active mode at startup (`INFERENCE: npu`, `SENSORS: bme680 + gp2y10 (MCU)`, etc.).

---

## 6. PHASE 0 — Contract (do this fully first) · Lead

### 6.1 Topics (`topics.py`)

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

### 6.2 JSON Schema (`packages/contract/schema/messages.schema.json`, draft 2020-12, `$defs` per type)

Key type — **now fully populated by real sensors**:
```jsonc
"SensorReading": {
  "type": "object",
  "required": ["schema_version","msg_type","ts","device_id","pm25","temperature","humidity"],
  "properties": {
    "schema_version": {"const": 1},
    "msg_type": {"const": "SensorReading"},
    "ts": {"type": "string","format": "date-time"},
    "device_id": {"type": "string"},
    "pm1_0": {"type": ["number","null"], "minimum": 0},   // null (GP2Y10 gives one value)
    "pm25":  {"type": "number", "minimum": 0},            // GP2Y10 dust proxy (µg/m³-equiv, dominant driver)
    "pm10":  {"type": ["number","null"], "minimum": 0},   // null; orchestrator derives ≈pm25×1.4
    "temperature": {"type": "number"},                    // BME
    "humidity":    {"type": "number","minimum":0,"maximum":100}, // BME
    "pressure":    {"type": ["number","null"]},           // BME (hPa)
    "voc_index":   {"type": ["number","null"], "minimum": 0},    // BME gas → index
    "source": {"type": "string", "enum": ["bme680+gp2y10","bme690+gp2y10","sim"]}
  }
}
```
Also define: **Profile** (`severity` mild/moderate/severe, `triggers[]`, `aqi_tolerance` 0–500, `humidity_threshold`, `medication`), **RiskAssessment** (`risk_score` 0–100, `risk_level` low/moderate/high/critical, `engine` npu/cpu/heuristic, `inference_ms`, `top_factors[]`, `advisory`, `advisory_source` llm/template), **ForecastUpdate** (`horizon_min`, `predictions{pm25[],humidity[]}`, `threshold_breach_min`, `safe_windows[]`), **EmergencyAlert** (`alert_id`, `user_id`, `risk_score`, `reason`, `recommended_action`, `safe_zone{name,lat,lon,distance_m}`), **EmergencyAck** (`alert_id`, `source` mobile/knob), **DeviceCommand** (`action` alarm_on/alarm_off/led/clear, `led_color` green/amber/red/off, `alert_id`), **DeviceStatus** (`online`, `role`), **CloudZoneUpdate** (`zones[]`, `outlook_48h`, `source` cloud_ai_100/template). Every payload carries `schema_version`, `msg_type`, `ts`.

- `models.py`: pydantic v2 models mirroring each type.
- `validate.py`: `validate(payload, msg_type)` via `jsonschema`.
- `docs/MQTT_CONTRACT.md`: topic table + one example payload per type (the mobile lane reads this to mirror DTOs).

**Acceptance:** `pip install -e packages/contract` works; `pytest tests/test_contract.py` passes.

---

## 7. PHASE 1 — Backend: broker + orchestrator · Backend

**Goal:** running orchestrator ingesting real telemetry, computing risk (heuristic to start), publishing risk, and running the cascade.

- **`ai_pc/broker/mosquitto.conf`:** `listener 1883 0.0.0.0` + `allow_anonymous true` + `persistence false`. README: install on Win ARM64 (`winget install EclipseFoundation.Mosquitto`), run `mosquitto -c ... -v`, open TCP 1883 in Windows Firewall, and how to find the LAN IP (`ipconfig`) → that IP is every device's `MQTT_HOST`.
- **`mqtt_client.py`:** paho wrapper — connect + auto-reconnect, LWT on `status/ai_pc`, subscribe to the topic set, dispatch by `msg_type`. Never crash on connect failure (retry/backoff).
- **`features.py`:** per-device rolling buffer (last ~10 min). Build the model input vector **from real values** (no derivation now):
  ```
  [ pm25, pm10, temperature, humidity, voc_index, pressure,
    pm25_rate_per_min, humidity_rate_per_min, temp_rate_per_min,
    severity_ordinal, personal_sensitivity ]        # keep as FEATURE_ORDER
  ```
  `personal_sensitivity = clamp(1 - aqi_tolerance/150, 0, 1)`. Rates = slope over the window. Share `FEATURE_ORDER` with `ai_pc/ml`.
- **`inference.py`** (ML lane owns internals): `RiskModel.predict(features) -> (score, level, engine, inference_ms, top_factors)`. Selection: **QNN/NPU → CPU → heuristic** (see §8). Level: `<25 low, <50 moderate, <75 high, ≥75 critical`. `top_factors` = the 2–3 biggest heuristic contribution terms (reuse `heuristic.py` to explain even when the NN produced the score). **P0 uses heuristic** so Phase 1 needs no ML.
- **`forecast.py` (P1):** Holt double-exponential smoothing on the buffer → predict pm25 & humidity for `horizon_min` (30). Compute `threshold_breach_min` and `safe_windows`. Publish every ~30 s.
- **`advisory.py` (P1):** Foundry Local single-sentence advisory with a 2 s timeout → **template fallback** on any error (see §8.6).
- **`cascade.py` — the hero:** per-user state machine `NORMAL → WATCH → EMERGENCY → ACKED` with **hysteresis + dwell**:
  | From | Event | To | Actions |
  |---|---|---|---|
  | NORMAL | score ≥ 50 for ≥2 readings | WATCH | LED **amber** |
  | WATCH | score ≥ 75 for ≥2 readings | EMERGENCY | **fire cascade** |
  | WATCH | score < 50 for ≥3 readings | NORMAL | LED **green** |
  | EMERGENCY | `EmergencyAck` | ACKED | buzzer **off**, LED amber, stop re-alerts |
  | EMERGENCY | no ack in 20 s | EMERGENCY | re-publish alert + re-buzz |
  | ACKED/EMERGENCY | score < 60 for ≥3 readings | NORMAL | LED green, `DeviceCommand{clear}` |

  **Fire cascade** (parallel, shared `alert_id` + timestamps): (1) `EmergencyAlert` on `emergency/alert`; (2) `DeviceCommand{alarm_on, led_color:red}` on `device/<id>/cmd`; (3) record `t_alert` for latency; nearest safe zone from `safe_zones.py`. Idempotent + logged. Unit-test hard.
- **`safe_zones.py`:** JSON list of clean-air zones (`name/lat/lon` — put 4–5 real venue/Mumbai coords). `nearest(lat,lon)` by haversine.
- **`simulator.py`:** `--sim` feeds synthetic telemetry (incl. a scripted spike) through the same pipeline, so the whole stack demos on the laptop with no board. Also expose a `/trigger_spike` endpoint as a stage backup.
- **`metrics.py`:** per-hop timestamps → mean inference ms, ingest→risk ms, cascade→ack ms.
- **`main.py`:** asyncio app — MQTT + handlers (`SensorReading`→features→inference→advisory→publish `RiskAssessment`; cascade tick; periodic forecast) + FastAPI (`/healthz`, `/state`, `/trigger_spike`). CLI `--sim`, `--no-npu`, `--no-foundry`.

**Deps (`ai_pc/requirements.txt`):** `paho-mqtt pydantic>=2 python-dotenv fastapi uvicorn numpy jsonschema statsmodels streamlit onnxruntime`. NPU + Foundry packages installed separately (§8), imported defensively.

**Acceptance:** `python -m ai_pc.orchestrator.main --sim` runs; dashboard shows a live risk gauge; the sim spike drives WATCH→EMERGENCY→publish alert→(fake ack)→NORMAL — zero hardware/ML/LLM.

---

## 8. PHASE 2 — ML: NPU model + benchmark (P1) · ML

**Goal:** a real quantized model on the **Snapdragon X Elite Hexagon NPU** + a CPU-vs-NPU benchmark. Drops into `inference.py` behind the same interface. **Inputs are now real sensor values**, so the demo shows the model reacting to genuine air changes.

- **`heuristic.py`:** documented bounded 0–100 score = weighted sum of normalized PM2.5 (dominant), humidity extremes, rapid temp drop, VOC, optional pressure drop, scaled by severity + personal sensitivity, plus spike penalties on positive rates. Returns score **and** per-term contributions (for `top_factors`). This is the label generator **and** the runtime fallback.
- **`gen_data.py`:** 30–50k synthetic samples across realistic ranges for **all real features** (pm25 0–400, pm10 0–500, temp 5–45 °C, humidity 10–95 %, voc 0–500, pressure 990–1030 hPa, plus profile), labeled by `heuristic()` + small noise. **Document that training data is synthetic** (honest hackathon choice) and that the model runs on real sensor inputs at inference. Same `FEATURE_ORDER` as §7.
- **`train_risk.py`:** PyTorch MLP `11 → 32 → 16 → 1`, ReLU, MSE, Adam; standardize inputs (fold scaler constants into the graph or ship them). Export `models/risk_fp32.onnx` (fixed shape `[1,11]`, opset 17).
- **`quantize.py` — RUN ON x64, commit the artifact:** ONNX Runtime's quantizer doesn't install cleanly on ARM64. **Quantize on an x64 machine / x64 Python, then commit `models/risk_int8.onnx`.** The ARM64 Surface only needs the `onnxruntime-qnn` inference wheel. Use static **QDQ INT8** with a calibration subset.
- **NPU session (canonical pattern in `inference.py`):** `pip install onnxruntime-qnn` on the Surface (Win ARM64 wheel; Hexagon driver ≥ 30.0.140.0).
  ```python
  import onnxruntime as ort
  providers = [
      ("QNNExecutionProvider", {
          "backend_path": "QnnHtp.dll", "htp_performance_mode": "burst",
          "qnn_context_cache_enable": "1",
          "qnn_context_cache_path": "ai_pc/ml/models/risk_qnn_ctx.bin"}),
      "CPUExecutionProvider",
  ]
  session = ort.InferenceSession("ai_pc/ml/models/risk_int8.onnx", providers=providers)
  engine = "npu" if session.get_providers()[0] == "QNNExecutionProvider" else "cpu"
  ```
  On any failure → stock `onnxruntime` CPU on `risk_fp32.onnx` → then heuristic. Log which engine loaded.
- **`advisory.py` LLM (Foundry Local):** `winget install Microsoft.FoundryLocal` + `pip install foundry-local-sdk-winml openai` (the **`-winml`** package = NPU/GPU on Windows; don't also install plain `foundry-local-sdk`).
  ```python
  import openai; from foundry_local import FoundryLocalManager
  m = FoundryLocalManager(os.getenv("FOUNDRY_MODEL","phi-4-mini"))   # auto-selects NPU variant on Snapdragon
  client = openai.OpenAI(base_url=m.endpoint, api_key=m.api_key)
  r = client.chat.completions.create(model=m.get_model_info("phi-4-mini").id,
        messages=[{"role":"system","content":ADVISORY_SYSTEM_PROMPT},
                  {"role":"user","content":json.dumps(ctx)}], max_tokens=60, timeout=2)
  ```
  Foundry Local is **preview (no SLA)** — expect failures, fall back to templates keyed on `level`+`top_factor`. Keep the prompt single-task ("one sentence, ≤30 words, what to do now").
- **`verify_npu.py`:** prints the active EP + a one-shot inference (proves NPU or reports fallback). **`benchmark.py`:** 1000 inferences NPU vs CPU → p50/p95 latency, throughput, energy proxy → `ai_pc/ml/benchmark.md` (a deck slide).

**Acceptance:** `verify_npu.py` shows `QNNExecutionProvider`; `benchmark.md` shows NPU ≤ CPU; orchestrator logs `INFERENCE: npu`.

---

## 9. PHASE 3 — Firmware: UNO Q with real sensors · Firmware

**Goal:** the MCU sketch reads BME (I²C) **and GP2Y1010 (analog + LED pulse)**, drives buzzer + LED, and bridges everything to Linux; `main.py` publishes. Runs off-hardware via a mock.

### 9.1 MCU sketch (`uno_q/sketch/sketch.ino`) — all sensing + actuation
- Include the BME library (`Adafruit_BME680` for 680, or Bosch `BME690` API for 690) + the `Modulino` library (Buzzer). Init BME over I²C at `BME_I2C_ADDR`. **Watch the `Wire`/`Wire1` gotcha** — set the correct I²C `Wire` instance for the UNO Q Qwiic/I²C bus; add a commented raw-`Wire` fallback.
- **BME read:** `temperature`, `humidity`, `pressure`, `gas_resistance`; compute `voc_index` from gas resistance vs a rolling baseline (§2.2).
- **GP2Y1010 read (§2.3):** pulse `DUST_LED_PIN` (LOW=on) → `delayMicroseconds(280)` → `analogRead(DUST_ADC_PIN)` → `delayMicroseconds(40)` → LED off, on a ~10 ms cycle; **median/average ~100 samples** for a stable reading; reconstruct `Vo` using `DUST_DIVIDER`, subtract `DUST_VOC_OFFSET`, convert to a µg/m³-equivalent `pm25` and clamp to [0,500]. Keep the pulse loop tight and non-blocking around the 10 ms cadence.
- **Expose all values over the Bridge** (`Bridge.provide/notify` — match your installed App Lab Bridge example's exact API): `pm25`, `temperature`, `humidity`, `pressure`, `voc_index`.
- Provide Bridge-callable functions the MPU invokes: `set_alarm(on)` → Modulino Buzzer tone pattern; `set_led(color)` → onboard MCU RGB LED (green/amber/red/off). *(Optional)* read Modulino Knob button → notify MPU (physical ack).
- Do **not** use `Serial1` (claimed by the Router). The ADC + pulse timing is exactly why this sensor lives on the MCU, not Linux.

### 9.2 MPU publisher (`uno_q/python/main.py`) — Bridge → MQTT only
- Pull **all** sensor values (`pm25`, `temperature`, `humidity`, `pressure`, `voc_index`) from the **Bridge**; assemble a `SensorReading` (`source` = `bme680+gp2y10` or `bme690+gp2y10`, `pm10`/`pm1_0` null); **publish to `telemetry/<DEVICE_ID>`** via paho-mqtt to `MQTT_HOST:1883` sub-minute. **No serial, no direct sensor I/O.**
- Subscribe to `device/<DEVICE_ID>/cmd`; on `alarm_on/led/alarm_off/clear`, call the Bridge to drive buzzer/LED. On knob-button notification, publish `EmergencyAck{source:"knob"}`.
- Publish retained `DeviceStatus{online:true, role:"uno_q"}` + set MQTT LWT.
- End with `App.run()` when running as an App Lab app.
- **`mock_hw.py`:** stand-in for the Bridge — synthetic BME + a synthetic `pm25` with a keyboard/auto-driven spike, and prints buzzer/LED actions. `main.py` auto-selects it when the real Bridge import fails or `--mock` is passed → `python uno_q/python/main.py --mock` runs the full publisher on any laptop.

### 9.3 App wiring & README
`app.yaml` is a **reference** — create the app in **Arduino App Lab**, paste in this `main.py`/`sketch.ino`. README: create the App Lab app, set Wi-Fi + `MQTT_HOST`; wire **BME (I²C)** and **GP2Y1010** (5 V Vcc + V-LED-through-150 Ω with 220 µF to GND; `LED` → `DUST_LED_PIN`; `Vo` → `DUST_ADC_PIN` through the divider, ≤3.3 V); flash the MCU; run (`arduino-app-cli app start ~/ArduinoApps/vayumitra`); view logs (`... app logs`). Include the `--mock` laptop path as the guaranteed fallback.

**Acceptance:** with the broker up, `python uno_q/python/main.py --mock` publishes valid `SensorReading`s; on hardware, **smoke/incense near the GP2Y1010 intake** clearly raises `pm25` and **alcohol near the BME** raises `voc_index` on the dashboard; a `DeviceCommand{alarm_on}` sounds the buzzer + red LED.

---

## 10. PHASE 4 — Mobile: Kotlin + Compose · Android

**Goal:** profile setup, live dashboard, and a **full-screen emergency** with one-tap Maps navigation + ack; plus an on-device model for offline risk.

- **Stack/deps (`build.gradle.kts`):** Kotlin, **Jetpack Compose**, MVVM (`ViewModel`+`StateFlow`), coroutines. MQTT: **HiveMQ client** `com.hivemq:hivemq-mqtt-client:1.3.x` pointed at `MQTT_HOST` (same local broker; Paho as fallback). On-device ML: **LiteRT/TFLite** with `risk.tflite` in `assets/`. JSON: `kotlinx.serialization`. `INTERNET` permission + cleartext to the LAN broker IP (dev network-security-config).
- **Package tree (`.../com/vayumitra/`):** `data/MqttService.kt` (sub risk/forecast/emergency; pub profile, ack), `data/Contract.kt` (topics + DTOs mirroring `MQTT_CONTRACT.md`), `data/RiskModel.kt` (LiteRT: NPU/NNAPI→GPU→CPU fallback), `model/` DTOs, `ui/ProfileScreen.kt` (severity, triggers, AQI tolerance, meds → publish retained `Profile`), `ui/DashboardScreen.kt` (risk gauge + real PM2.5/VOC/temp/humidity + advisory + `threshold_breach_min` + safe windows), `ui/EmergencyScreen.kt` (full-screen red: reason, **Navigate to <zone>** → `Intent(ACTION_VIEW, geo:lat,lon?q=…)` to Google Maps, **I'm safe** → publish `EmergencyAck{source:"mobile"}`), `MainActivity.kt`, `VayuViewModel.kt`.
- **Behaviors:** profile save personalizes immediately; dashboard shows live risk; `EmergencyAlert` forces the full-screen screen (use a full-screen/heads-up notification so it shows even if backgrounded); on-device `risk.tflite` computes a local risk from the latest reading so the phone still shows risk if the AI PC/broker drops (offline capability = talking point). Convert `risk_fp32.onnx`→`risk.tflite` in `ai_pc/ml` and commit to `assets/`. Publish retained `DeviceStatus{role:"mobile"}`.

**Acceptance:** app connects, shows live risk, flips to full-screen emergency when the cascade fires, "Navigate" opens Maps to the safe zone, "I'm safe" clears the cascade (buzzer stops). With Wi-Fi off, the on-device model still renders a risk value.

---

## 11. PHASE 5 — Cloud aggregator (P2) · Cloud

`cloud/aggregator.py`: subscribe to `emergency/alert` (+ optional telemetry), bucket into geo **zones** using `DEVICE_LAT/LON` (+ a small synthetic fleet), publish `CloudZoneUpdate` on `cloud/zones` (retained) with a 24–48 h outlook. If a real **Qualcomm Cloud AI 100 / Cirrascale** endpoint is configured, call it; otherwise a deterministic **template forecast** (`source:"template"`). `zones.py`: geo-bucketing + haversine. README: how it *would* deploy on Cloud AI 100; offline path runs locally for the demo.

**Acceptance:** `python -m cloud.aggregator` publishes a `CloudZoneUpdate` the dashboard/phone can show.

---

## 12. Dashboard (`ai_pc/dashboard/app.py`)

Streamlit (`streamlit run ai_pc/dashboard/app.py`, :8501), subscribing to the broker in a background thread: live PM2.5/temp/humidity/VOC charts; risk gauge colored by level with an **engine badge** (NPU/CPU/heuristic) + inference ms; **cascade panel** (state + last alert_id + big green/amber/red mirroring the LED); **latency HUD** (ingest→risk, cascade→ack, model p50 from `benchmark.md`); forecast + safe windows; zones (if cloud up); a **"Trigger demo spike"** button (`/trigger_spike`) as stage backup. Keep it legible from across the room.

---

## 13. Run it — `infra/scripts/`

- **`setup.ps1`:** create `.venv`, `pip install -r ai_pc/requirements.txt`, `pip install -e packages/contract`, copy `.env.example`→`.env`, print next steps (install Mosquitto, `onnxruntime-qnn`, Foundry Local; set `MQTT_HOST`).
- **`run_all.ps1`:** start Mosquitto → orchestrator (`--sim` if `-Sim`) → dashboard; print the LAN IP + the `MQTT_HOST` to enter on the phone and UNO Q; remind to start those two. `-Sim` runs the whole stack with no peripherals (demo insurance).
- **`stop_all.ps1`:** stop the started processes.

**Acceptance:** clean Surface → `setup.ps1` then `run_all.ps1 -Sim` brings up broker + orchestrator + dashboard and the sim drives a full cascade.

---

## 14. Testing (`tests/`)

- `test_contract.py`: valid + invalid payload per type → `validate()` passes/raises.
- `test_heuristic.py`: bounded [0,100]; monotonic in pm25; severe ≥ mild for identical inputs; a PM spike raises score.
- `test_cascade.py`: dwell required for EMERGENCY; ack → ACKED stops re-alerts; hysteresis prevents flapping; clear returns to NORMAL (fake clock).
- `test_smoke_e2e.py`: publish a synthetic `SensorReading` → assert `RiskAssessment`; a spike → assert `EmergencyAlert`.

---

## 15. Demo (~4 min) — `docs/DEMO_SCRIPT.md`

1. **Setup (15s):** dashboard green, phone low risk, LED green. "Four devices, one Wi-Fi, no cloud in the loop."
2. **Real data (20s):** breathe on the BME → humidity/temp move live on dashboard + phone. "Genuine hyperlocal sensing, sub-minute, on the edge."
3. **The spike (40s):** "Pollution rises nearby." Trigger a **real spike** — the GP2Y1010 is a smoke-detector part, so a **wisp of incense / a just-blown-out match near its intake** spikes `pm25` fast and reliably; **hand sanitizer / an alcohol wipe near the BME** spikes `voc_index` instantly (a good smoke-free option). Risk climbs green→amber (LED amber) → **crosses critical** → **all four fire at once:** buzzer + red LED, phone full-screen alert with the personalized advisory, dashboard cascade red, cloud zone flagged. Call out the **cross-device latency** on the HUD.
4. **Personalized + predictive (30s):** show the on-device-LLM advisory sentence + the forecast ("indoor advised in ~25 min; safe window 6–7 pm"), tailored to this user's profile.
5. **Act & resolve (25s):** tap **Navigate** → Maps routes to the nearest clean-air zone; tap **I'm safe** (or the Knob button) → buzzer stops, everything de-escalates to green. Closed loop.
6. **Edge proof (25s):** **turn Wi-Fi off** on the phone → on-device model still shows risk. Then show the **NPU-vs-CPU benchmark** slide — "risk inference runs on the Hexagon NPU."
7. **Close:** "Sensing on the microcontroller, intelligence on the NPU, action on the phone, scale in the cloud — impossible on one device."

*Backup if a live spike is slow to clear:* `run_all.ps1 -Sim` + the dashboard "Trigger demo spike" button reproduces steps 3–5.

---

## 16. README + submission (Lead; blocking)

README in order: **app description** (+ architecture diagram + the cascade); **dev names + emails**; **setup from scratch** (Python 3.11, Mosquitto, JDK/Android Studio, App Lab, `onnxruntime-qnn`, Foundry Local, and the GP2Y1010 external parts — **150 Ω resistor + 220 µF cap + a Vo resistor divider** — list every dependency, and the `setup.ps1` step); **run & usage** (`run_all.ps1`, starting UNO Q + mobile, which `MQTT_HOST`); **license = MIT** (`LICENSE` at root; state that the majority runs on the edge, cloud is optional); **testing** (`pytest -q`); **notes** (synthetic training data; GP2Y1010 is a *relative* dust proxy needing per-unit calibration; BME680-vs-690 library choice; Foundry Local is preview); **references** (Arduino UNO Q + App Lab, BME680/690 + BSEC, Sharp GP2Y1010AU0F datasheet, ONNX Runtime QNN, Foundry Local, HiveMQ, LiteRT). Then **submit the repo link via the Microsoft Form by the deadline** and confirm it runs from the README.

---

## 17. Timeline · lanes · cut-list

**Lanes (folder = boundary; contract is the only coupling):** Lead → `packages/contract/`, `docs/`, `infra/scripts/`, README/LICENSE. Backend → `ai_pc/orchestrator|dashboard|broker`. ML → `ai_pc/ml`. Firmware → `uno_q/`. Android → `mobile/`. Cloud → `cloud/` (P2). *(3–5 people: Lead+Cloud together, then Backend, ML, Firmware, Android.)*

**30 hours:**
- **H0–H2 (all):** scaffold + **contract frozen**; everyone `pip install -e packages/contract`; agree `MQTT_HOST`, `FEATURE_ORDER`.
- **H2–H8:** Backend Phase-1 slice in `--sim` (heuristic + cascade + dashboard); Firmware `main.py --mock` publishing; Android MQTT connect + Dashboard; ML starts `heuristic.py` + `gen_data.py`. **By H8: synthetic reading → visible cascade end-to-end.**
- **H8–H16:** Firmware on real hardware — **BME (I²C) + GP2Y1010 (analog, pulse+ADC) + buzzer + LED**; Android emergency + Maps + ack + Profile; ML train → export → **quantize (x64)** → `verify_npu` on Surface; Cloud skeleton. **By H16: real-sensor cascade on the LAN; phone ack clears it.**
- **H16–H22:** drop NPU model into `inference.py` + `benchmark.py`; Foundry Local advisories (+ template); forecast + safe windows; on-device model on phone; latency HUD.
- **H22–H26:** integration hardening — kill each software dependency in turn (NPU, Foundry, cloud, Wi-Fi) and confirm graceful degradation; tune cascade thresholds on real data; polish UI.
- **H26–H29:** docs + `benchmark.md` + demo script; rehearse the demo twice incl. `-Sim` backup; commit model artifacts.
- **H29–H30:** final commit, tag, **submit the form**. Buffer.

**Cut-list if behind (drop from bottom):** Cloud → on-device phone model (phone shows AI-PC risk) → Foundry Local (templates) → forecast. **Never cut:** contract, the cascade, real telemetry (BME+GP2Y10), phone emergency + ack, dashboard.

---

## 18. Definition of done

- `run_all.ps1 -Sim` on a clean Surface → full cascade, no peripherals.
- With hardware on the LAN: smoke/incense near the GP2Y1010 (PM2.5) or alcohol near the BME (VOC) spike → buzzer + red LED + phone full-screen + Maps nav + ack clears it; dashboard shows `engine=npu` + a real latency number.
- Phone works with Wi-Fi off (on-device model). `verify_npu.py` → `QNNExecutionProvider`; `benchmark.md` shows NPU ≤ CPU.
- `pytest -q` green. README runs from scratch. Repo submitted before the deadline under MIT.
