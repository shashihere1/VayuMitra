"""Prove the NPU is live: print the active execution provider and run one
inference.  Reports a graceful fallback if QNN/NPU isn't available.

Run on the Snapdragon Surface (needs onnxruntime-qnn):
    python -m ai_pc.ml.verify_npu
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

_MODELS = Path(__file__).resolve().parent / "models"


def main() -> None:
    try:
        import onnxruntime as ort
    except Exception as e:
        raise SystemExit(f"onnxruntime not installed: {e}")

    int8 = _MODELS / "risk_int8.onnx"
    fp32 = _MODELS / "risk_fp32.onnx"
    model = int8 if int8.is_file() else fp32
    if not model.is_file():
        raise SystemExit("no model found; train + quantize first "
                         "(gen_data -> train_risk -> quantize)")

    providers = [
        ("QNNExecutionProvider", {
            "backend_path": "QnnHtp.dll",
            "htp_performance_mode": "burst",
            "qnn_context_cache_enable": "1",
            "qnn_context_cache_path": str(_MODELS / "risk_qnn_ctx.bin"),
        }),
        "CPUExecutionProvider",
    ]

    print("available providers:", ort.get_available_providers())
    try:
        sess = ort.InferenceSession(str(model), providers=providers)
    except Exception as e:
        print(f"QNN session failed ({e}); retrying CPU-only")
        sess = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])

    active = sess.get_providers()[0]
    engine = "npu" if active == "QNNExecutionProvider" else "cpu"
    print(f"ACTIVE provider: {active}   -> engine={engine}")

    name = sess.get_inputs()[0].name
    n_feat = sess.get_inputs()[0].shape[-1]
    x = np.zeros((1, int(n_feat) if isinstance(n_feat, int) else 11), dtype=np.float32)
    out = sess.run(None, {name: x})
    print(f"one-shot inference on {model.name}: risk={float(out[0].reshape(-1)[0]):.2f}")

    if engine == "npu":
        print("SUCCESS: risk inference is running on the Hexagon NPU (QNN EP).")
    else:
        print("NOTE: running on CPU fallback (NPU/QNN not active on this machine).")


if __name__ == "__main__":
    main()
