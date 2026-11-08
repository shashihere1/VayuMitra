# Mobile — Kotlin + Jetpack Compose (Android)

Profile setup, a live dashboard, and a **full-screen emergency** with one-tap
Google Maps navigation + ack. An on-device model computes risk offline.

## Build & run

Open `mobile/` in **Android Studio** (Giraffe+), let it sync, then Run on a
device/emulator. Or from the CLI (needs a Gradle wrapper — generate once with
`gradle wrapper` in `mobile/`, or use Android Studio's bundled Gradle):

```bash
cd mobile
./gradlew installDebug -PMQTT_HOST=192.168.1.42 -PUSER_ID=demo-user
```

- `MQTT_HOST` — the AI PC's LAN IP (default `10.0.2.2` = host loopback from the
  Android emulator). On a real phone use the actual LAN IP.
- The emulator reaches a broker on the host machine via `10.0.2.2`.

## Architecture (`com.vayumitra`)

| File | Role |
|---|---|
| `data/Contract.kt` | MQTT topics (mirror `topics.py`) |
| `model/Dtos.kt` | `@Serializable` DTOs mirroring `docs/MQTT_CONTRACT.md` |
| `data/MqttService.kt` | HiveMQ client: sub risk/forecast/emergency/telemetry; pub profile + ack (+ LWT) |
| `data/RiskModel.kt` | LiteRT/TFLite (NNAPI→CPU) with a Kotlin heuristic fallback |
| `VayuViewModel.kt` | MVVM: `StateFlow<UiState>`, offline watchdog |
| `ui/DashboardScreen.kt` | risk gauge + live PM2.5/VOC/temp/humidity + advisory + forecast |
| `ui/EmergencyScreen.kt` | full-screen red: reason, **Navigate to zone**, **I'm safe** (ack) |
| `ui/ProfileScreen.kt` | severity, triggers, AQI tolerance, meds → retained `Profile` |
| `MainActivity.kt` | nav + emergency takeover |

## Behaviors

- Saving the profile publishes a **retained** `Profile`, personalizing risk
  immediately.
- The dashboard shows live risk from the AI PC (`risk/<user>`).
- An `EmergencyAlert` for this user flips the whole app to the red emergency
  screen. **Navigate** opens Google Maps to the nearest safe zone;
  **I'm safe** publishes `EmergencyAck{source:"mobile"}` (clears the cascade,
  silences the buzzer).
- **Offline capability:** if AI-PC risk goes stale (>6 s) or Wi-Fi drops, the
  on-device model computes risk from the last cached reading — the gauge keeps
  updating. Add `app/src/main/assets/risk.tflite` (+ `scaler.json`) for the real
  NN path; otherwise the Kotlin heuristic is used.

## On-device model

```bash
python -m ai_pc.ml.to_tflite   # writes app/src/main/assets/risk.tflite
cp ai_pc/ml/models/scaler.json mobile/app/src/main/assets/   # optional
```
