"""Risk inference with graceful degradation: **QNN/NPU -> CPU -> heuristic**.

``RiskModel.predict(features) -> (score, level, engine, inference_ms, top_factors)``

The neural model is optional.  If ``risk_int8.onnx`` / ``risk_fp32.onnx`` and
onnxruntime are present, we run them (preferring the Hexagon NPU via the QNN
execution provider); otherwise we fall back to the pure-Python heuristic.

``top_factors`` is *always* computed from the heuristic's per-term
contributions — so even when the neural net produces the score, we can still
explain which drivers dominated.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ai_pc.ml.heuristic import heuristic, level_for, top_factors
from ai_pc.orchestrator.features import to_vector

log = logging.getLogger("vayumitra.inference")

_MODELS_DIR = Path(__file__).resolve().parents[1] / "ml" / "models"
_INT8 = _MODELS_DIR / "risk_int8.onnx"
_FP32 = _MODELS_DIR / "risk_fp32.onnx"
_SCALER = _MODELS_DIR / "scaler.json"
_QNN_CTX = _MODELS_DIR / "risk_qnn_ctx.bin"


class RiskModel:
    def __init__(self, use_npu: bool = True) -> None:
        self.engine = "heuristic"
        self._session = None
        self._input_name: Optional[str] = None
        self._scaler_mean: Optional[List[float]] = None
        self._scaler_std: Optional[List[float]] = None
        self._load(use_npu)

    # --- loading ---------------------------------------------------------- #
    def _load_scaler(self) -> None:
        if _SCALER.is_file():
            try:
                d = json.loads(_SCALER.read_text(encoding="utf-8"))
                self._scaler_mean = d.get("mean")
                self._scaler_std = d.get("std")
            except Exception as e:
                log.warning("could not read scaler.json (%s); using raw inputs", e)

    def _load(self, use_npu: bool) -> None:
        try:
            import onnxruntime as ort  # noqa: WPS433 (optional dep)
        except Exception:
            log.info("onnxruntime not installed -> heuristic engine")
            return

        self._load_scaler()

        # Choose model file: INT8 for NPU path, else FP32.
        model_path = _INT8 if (use_npu and _INT8.is_file()) else _FP32
        if not model_path.is_file():
            log.info("no ONNX model at %s -> heuristic engine", model_path)
            return

        providers: list = []
        if use_npu:
            providers.append((
                "QNNExecutionProvider",
                {
                    "backend_path": "QnnHtp.dll",
                    "htp_performance_mode": "burst",
                    "qnn_context_cache_enable": "1",
                    "qnn_context_cache_path": str(_QNN_CTX),
                },
            ))
        providers.append("CPUExecutionProvider")

        try:
            self._session = ort.InferenceSession(str(model_path), providers=providers)
            active = self._session.get_providers()[0]
            self.engine = "npu" if active == "QNNExecutionProvider" else "cpu"
            self._input_name = self._session.get_inputs()[0].name
            log.info("loaded %s on %s (engine=%s)", model_path.name, active, self.engine)
        except Exception as e:
            # QNN can fail to init on non-Snapdragon / missing driver; retry CPU.
            log.warning("QNN/NPU session failed (%s); trying CPU-only", e)
            try:
                self._session = ort.InferenceSession(
                    str(_FP32 if _FP32.is_file() else model_path),
                    providers=["CPUExecutionProvider"],
                )
                self.engine = "cpu"
                self._input_name = self._session.get_inputs()[0].name
                log.info("loaded CPU session (engine=cpu)")
            except Exception as e2:
                log.warning("CPU session also failed (%s) -> heuristic engine", e2)
                self._session = None
                self.engine = "heuristic"

    # --- inference -------------------------------------------------------- #
    def _standardize(self, vec: List[float]) -> List[float]:
        if self._scaler_mean and self._scaler_std:
            return [
                (v - m) / (s if s else 1.0)
                for v, m, s in zip(vec, self._scaler_mean, self._scaler_std)
            ]
        return vec

    def predict(self, features: Dict[str, float]) -> Tuple[float, str, str, float, List[str]]:
        # Heuristic always runs — cheap, and it produces the explanation.
        h_score, contributions = heuristic(features)
        factors = top_factors(contributions, n=3)

        if self._session is None:
            return round(h_score, 1), level_for(h_score), "heuristic", 0.0, factors

        try:
            import numpy as np

            vec = self._standardize(to_vector(features))
            arr = np.asarray([vec], dtype=np.float32)
            t0 = time.perf_counter()
            out = self._session.run(None, {self._input_name: arr})
            ms = (time.perf_counter() - t0) * 1000.0
            score = float(out[0].reshape(-1)[0])
            score = max(0.0, min(100.0, score))
            return round(score, 1), level_for(score), self.engine, round(ms, 3), factors
        except Exception as e:
            log.warning("neural inference failed at runtime (%s) -> heuristic", e)
            return round(h_score, 1), level_for(h_score), "heuristic", 0.0, factors
