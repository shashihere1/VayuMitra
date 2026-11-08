# assets/

Place the on-device model here:

- `risk.tflite` — produced by `python -m ai_pc.ml.to_tflite` (copied here
  automatically by that script).
- `scaler.json` — optional; copy from `ai_pc/ml/models/scaler.json` so the
  TFLite inputs are standardized the same way as training.

**Both are optional.** If `risk.tflite` is absent, `RiskModel` falls back to a
Kotlin port of the documented heuristic, so the phone still shows a risk value
offline (the demo's "Wi-Fi off" talking point).
