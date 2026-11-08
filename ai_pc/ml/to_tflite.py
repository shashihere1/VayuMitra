"""Convert ``risk_fp32.onnx`` -> ``risk.tflite`` for the phone's on-device model.

The mobile lane runs LiteRT/TFLite; commit the produced ``risk.tflite`` into
``mobile/app/src/main/assets/``.  Conversion is ONNX -> TF SavedModel -> TFLite
via the ``onnx2tf`` toolchain.

This is fiddly and platform-dependent, so it's isolated here and optional (the
phone falls back to showing the AI-PC risk if the local model is absent).

Run (x64, needs: pip install onnx2tf tensorflow onnx onnxruntime):
    python -m ai_pc.ml.to_tflite
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FP32 = _HERE / "models" / "risk_fp32.onnx"
_SAVED = _HERE / "models" / "_tf_saved"
_TFLITE = _HERE / "models" / "risk.tflite"
_ASSETS = _HERE.parents[1] / "mobile" / "app" / "src" / "main" / "assets"


def main() -> None:
    if not _FP32.is_file():
        raise SystemExit(f"missing {_FP32}; run train_risk first")
    try:
        import onnx2tf  # noqa: F401
    except Exception:
        raise SystemExit("pip install onnx2tf tensorflow onnx onnxruntime")

    # onnx2tf emits a SavedModel + a float32 tflite by default.
    cmd = [sys.executable, "-m", "onnx2tf", "-i", str(_FP32),
           "-o", str(_SAVED), "-osd"]
    print("running:", " ".join(cmd))
    subprocess.check_call(cmd)

    # onnx2tf writes <name>_float32.tflite into the output dir; pick the first.
    candidates = sorted(_SAVED.glob("*float32.tflite")) or sorted(_SAVED.glob("*.tflite"))
    if not candidates:
        raise SystemExit(f"no .tflite produced in {_SAVED}")
    shutil.copy(candidates[0], _TFLITE)
    print(f"wrote {_TFLITE}")

    _ASSETS.mkdir(parents=True, exist_ok=True)
    shutil.copy(_TFLITE, _ASSETS / "risk.tflite")
    print(f"copied to {_ASSETS / 'risk.tflite'} (commit this)")


if __name__ == "__main__":
    main()
