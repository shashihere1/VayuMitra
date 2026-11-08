"""Static QDQ INT8 quantization of ``risk_fp32.onnx`` -> ``risk_int8.onnx``.

RUN THIS ON x64 and COMMIT THE ARTIFACT.  ONNX Runtime's quantizer does not
install cleanly on Windows ARM64; the ARM64 Surface only needs the
``onnxruntime-qnn`` *inference* wheel.  So: quantize on an x64 box, commit
``models/risk_int8.onnx``, and the Snapdragon just loads it.

Run (on x64, needs onnx + onnxruntime):
    python -m ai_pc.ml.quantize
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_DATA = _HERE / "data" / "train.npz"
_MODELS = _HERE / "models"
_FP32 = _MODELS / "risk_fp32.onnx"
_INT8 = _MODELS / "risk_int8.onnx"


def _calibration_reader(n_samples: int):
    """A CalibrationDataReader over a standardized subset of the training data."""
    import json

    from onnxruntime.quantization import CalibrationDataReader

    d = np.load(_DATA, allow_pickle=True)
    X = d["X"].astype(np.float32)
    scaler = json.loads((_MODELS / "scaler.json").read_text(encoding="utf-8"))
    mean = np.array(scaler["mean"], dtype=np.float32)
    std = np.array(scaler["std"], dtype=np.float32)
    std[std == 0] = 1.0
    Xs = (X[:n_samples] - mean) / std

    class _Reader(CalibrationDataReader):
        def __init__(self):
            self._it = iter([{"features": row.reshape(1, -1)} for row in Xs])

        def get_next(self):
            return next(self._it, None)

    return _Reader()


def main() -> None:
    p = argparse.ArgumentParser(description="static INT8 (QDQ) quantization")
    p.add_argument("--calib", type=int, default=512, help="calibration subset size")
    args = p.parse_args()

    if not _FP32.is_file():
        raise SystemExit(f"missing {_FP32}; run `python -m ai_pc.ml.train_risk` first")

    from onnxruntime.quantization import QuantFormat, QuantType, quantize_static

    quantize_static(
        model_input=str(_FP32),
        model_output=str(_INT8),
        calibration_data_reader=_calibration_reader(args.calib),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QInt8,
        weight_type=QuantType.QInt8,
        per_channel=False,
    )
    print(f"wrote {_INT8}  (static QDQ INT8, calib={args.calib})")
    print("COMMIT this file; the ARM64 Surface loads it via onnxruntime-qnn.")


if __name__ == "__main__":
    main()
