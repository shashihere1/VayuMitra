"""Per-device rolling feature engineering.

Keeps the last ~10 minutes of readings per device and turns the latest reading
(plus the user's profile) into the canonical ``FEATURE_ORDER`` vector consumed
by both the neural model and the heuristic.

Rates are least-squares slopes over the window, expressed per minute.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Tuple

from ai_pc.ml.heuristic import FEATURE_ORDER, SEVERITY_ORDINAL

WINDOW_SECONDS = 600  # 10 minutes


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _slope_per_min(samples: list[Tuple[float, float]]) -> float:
    """Least-squares slope of value vs time (seconds) scaled to per-minute.

    ``samples`` is a list of ``(t_seconds, value)``. Returns 0 with <2 points.
    """
    n = len(samples)
    if n < 2:
        return 0.0
    t0 = samples[0][0]
    xs = [t - t0 for t, _ in samples]
    ys = [v for _, v in samples]
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    slope_per_sec = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return slope_per_sec * 60.0


@dataclass
class DeviceBuffer:
    device_id: str
    pm25: Deque[Tuple[float, float]] = field(default_factory=deque)
    humidity: Deque[Tuple[float, float]] = field(default_factory=deque)
    temperature: Deque[Tuple[float, float]] = field(default_factory=deque)
    latest: Optional[dict] = None

    def _trim(self, dq: Deque[Tuple[float, float]], now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        while dq and dq[0][0] < cutoff:
            dq.popleft()

    def add(self, reading: dict, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self.latest = reading
        self.pm25.append((now, float(reading.get("pm25") or 0.0)))
        self.humidity.append((now, float(reading.get("humidity") or 0.0)))
        self.temperature.append((now, float(reading.get("temperature") or 0.0)))
        for dq in (self.pm25, self.humidity, self.temperature):
            self._trim(dq, now)

    def rates(self) -> Dict[str, float]:
        return {
            "pm25_rate_per_min": _slope_per_min(list(self.pm25)),
            "humidity_rate_per_min": _slope_per_min(list(self.humidity)),
            "temp_rate_per_min": _slope_per_min(list(self.temperature)),
        }


class FeatureStore:
    """Holds one buffer per device_id."""

    def __init__(self) -> None:
        self._buffers: Dict[str, DeviceBuffer] = {}

    def add_reading(self, reading: dict, now: Optional[float] = None) -> DeviceBuffer:
        did = reading.get("device_id", "unknown")
        buf = self._buffers.get(did)
        if buf is None:
            buf = self._buffers[did] = DeviceBuffer(device_id=did)
        buf.add(reading, now=now)
        return buf

    def buffer(self, device_id: str) -> Optional[DeviceBuffer]:
        return self._buffers.get(device_id)


def personal_sensitivity(profile: Optional[dict]) -> float:
    """clamp(1 - aqi_tolerance/150, 0, 1). Higher = more sensitive user."""
    tol = 100.0
    if profile:
        tol = float(profile.get("aqi_tolerance", 100.0) or 100.0)
    return _clamp(1.0 - tol / 150.0, 0.0, 1.0)


def build_features(
    reading: dict,
    buf: DeviceBuffer,
    profile: Optional[dict] = None,
) -> Dict[str, float]:
    """Assemble the named feature dict in ``FEATURE_ORDER``.

    pm10 is derived (~pm25 * 1.4) when the sensor reports null, per the plan.
    """
    pm25 = float(reading.get("pm25") or 0.0)
    pm10 = reading.get("pm10")
    pm10 = float(pm10) if pm10 is not None else pm25 * 1.4

    rates = buf.rates()
    severity = SEVERITY_ORDINAL.get((profile or {}).get("severity", "moderate"), 1)

    feats: Dict[str, float] = {
        "pm25": pm25,
        "pm10": pm10,
        "temperature": float(reading.get("temperature") or 0.0),
        "humidity": float(reading.get("humidity") or 0.0),
        "voc_index": float(reading.get("voc_index") or 0.0),
        "pressure": float(reading.get("pressure") or 0.0),
        "pm25_rate_per_min": rates["pm25_rate_per_min"],
        "humidity_rate_per_min": rates["humidity_rate_per_min"],
        "temp_rate_per_min": rates["temp_rate_per_min"],
        "severity_ordinal": float(severity),
        "personal_sensitivity": personal_sensitivity(profile),
    }
    # Guarantee ordering / completeness.
    return {k: feats[k] for k in FEATURE_ORDER}


def to_vector(feats: Dict[str, float]) -> list[float]:
    return [float(feats[k]) for k in FEATURE_ORDER]
