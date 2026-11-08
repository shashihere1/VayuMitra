"""Latency instrumentation.  Every hop stamps a timestamp; this module keeps
rolling means/p50/p95 for the dashboard HUD.

All times are ``time.perf_counter()`` seconds; helpers convert to milliseconds.
"""
from __future__ import annotations

import time
from collections import deque
from statistics import mean
from typing import Deque, Dict


def _pct(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


class Metrics:
    """Thread-safe-enough single-writer metrics store (asyncio single loop)."""

    def __init__(self, window: int = 200) -> None:
        self._series: Dict[str, Deque[float]] = {}
        self._window = window

    def record(self, name: str, ms: float) -> None:
        buf = self._series.get(name)
        if buf is None:
            buf = self._series[name] = deque(maxlen=self._window)
        buf.append(float(ms))

    def record_since(self, name: str, t0: float) -> float:
        ms = (time.perf_counter() - t0) * 1000.0
        self.record(name, ms)
        return ms

    def summary(self, name: str) -> dict:
        buf = self._series.get(name)
        if not buf:
            return {"n": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "last_ms": 0.0}
        vals = list(buf)
        s = sorted(vals)
        return {
            "n": len(vals),
            "mean_ms": round(mean(vals), 2),
            "p50_ms": round(_pct(s, 0.50), 2),
            "p95_ms": round(_pct(s, 0.95), 2),
            "last_ms": round(vals[-1], 2),
        }

    def all(self) -> dict:
        return {name: self.summary(name) for name in self._series}


# Shared singleton the orchestrator writes to and the API/dashboard reads.
METRICS = Metrics()


def now() -> float:
    return time.perf_counter()
