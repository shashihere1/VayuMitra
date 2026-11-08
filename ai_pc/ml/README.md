# ML lane — risk model on the Snapdragon NPU

A real quantized MLP that drops into `orchestrator/inference.py` behind the same
interface (`NPU -> CPU -> heuristic`). Inputs are **real** sensor values; the
training *labels* are synthetic (disclosed — see below).

## Feature vector (`FEATURE_ORDER`, 11 dims)

```
[ pm25, pm10, temperature, humidity, voc_index, pressure,
  pm25_rate_per_min, humidity_rate_per_min, temp_rate_per_min,
  severity_ordinal, personal_sensitivity ]
```
Defined once in `heuristic.py` and shared with `orchestrator/features.py`.

## Pipeline

```bash
# 1. synthetic dataset (labels from the documented heuristic + noise)
python -m ai_pc.ml.gen_data --n 40000

# 2. train the MLP -> models/risk_fp32.onnx (+ models/scaler.json)
python -m ai_pc.ml.train_risk            # needs: pip install torch onnx

# 3. QUANTIZE ON x64, then COMMIT the artifact
python -m ai_pc.ml.quantize              # -> models/risk_int8.onnx  (QDQ INT8)

# 4. on the Snapdragon Surface (pip install onnxruntime-qnn):
python -m ai_pc.ml.verify_npu            # prints QNNExecutionProvider
python -m ai_pc.ml.benchmark             # -> benchmark.md (NPU vs CPU)

# 5. (optional) phone model
python -m ai_pc.ml.to_tflite             # -> mobile assets/risk.tflite
```

## Why quantize on x64?

ONNX Runtime's quantizer doesn't install cleanly on Windows ARM64. Quantize on
any x64 machine/Python, **commit `models/risk_int8.onnx`**, and the ARM64
Surface only needs the `onnxruntime-qnn` *inference* wheel (Hexagon driver
≥ 30.0.140.0).

## NPU session (canonical pattern — see `inference.py`)

```python
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

On any failure the code degrades to stock `onnxruntime` CPU on `risk_fp32.onnx`,
then to the pure-Python `heuristic`. The orchestrator logs which engine loaded.

## Honesty note

Training data is **synthetic** — sampled across realistic ranges and labeled by
`heuristic()`. This is a disclosed hackathon choice: it lets us ship a real
NPU-quantized model without a labeled field dataset. At inference the model
consumes **real** BME + GP2Y1010 readings, and the same heuristic is the runtime
fallback and the explainer for `top_factors`.
