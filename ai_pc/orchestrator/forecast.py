"""Short-horizon forecast (P1).

Holt double-exponential smoothing on the rolling buffer to project pm25 and
humidity ``horizon_min`` ahead (default 30 min).  Computes the first
``threshold_breach_min`` (when pm25 is projected to cross a threshold) and any
``safe_windows`` (contiguous minutes projected below it).

Uses a tiny dependency-free Holt implementation so it runs even where
``statsmodels`` isn't installed; statsmodels is used opportunistically if
available for the pm25 series.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("vayumitra.forecast")

STEP_MIN = 1  # forecast resolution in minutes


def _holt(series: List[float], horizon: int,
          alpha: float = 0.5, beta: float = 0.3) -> List[float]:
    """Dependency-free Holt linear (double-exponential) forecast.

    Returns ``horizon`` future point estimates. Falls back to flat/naive with
    short series.
    """
    n = len(series)
    if n == 0:
        return [0.0] * horizon
    if n == 1:
        return [series[0]] * horizon

    level = series[0]
    trend = series[1] - series[0]
    for i in range(1, n):
        prev_level = level
        level = alpha * series[i] + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return [level + (h + 1) * trend for h in range(horizon)]


def _values(samples: List[Tuple[float, float]]) -> List[float]:
    return [v for _, v in samples]


def forecast_series(buf, horizon_min: int = 30) -> Dict[str, List[float]]:
    """Project pm25 and humidity for the horizon (one point per minute)."""
    steps = max(1, horizon_min // STEP_MIN)
    pm25_hist = _values(list(buf.pm25))
    hum_hist = _values(list(buf.humidity))

    # Opportunistically use statsmodels for pm25 if enough history.
    pm25_pred: Optional[List[float]] = None
    if len(pm25_hist) >= 6:
        try:
            from statsmodels.tsa.holtwinters import Holt  # type: ignore

            fit = Holt(pm25_hist, initialization_method="estimated").fit(
                optimized=True
            )
            pm25_pred = [max(0.0, float(x)) for x in fit.forecast(steps)]
        except Exception as e:
            log.debug("statsmodels Holt unavailable/failed (%s); using builtin", e)

    if pm25_pred is None:
        pm25_pred = [max(0.0, x) for x in _holt(pm25_hist, steps)]
    hum_pred = [min(100.0, max(0.0, x)) for x in _holt(hum_hist, steps)]

    return {"pm25": pm25_pred, "humidity": hum_pred}


def threshold_breach_min(pm25_pred: List[float], threshold: float) -> Optional[float]:
    """Minutes until pm25 is first projected to exceed ``threshold`` (or None)."""
    for i, v in enumerate(pm25_pred):
        if v >= threshold:
            return (i + 1) * STEP_MIN
    return None


def safe_windows(pm25_pred: List[float], threshold: float) -> List[Dict[str, float]]:
    """Contiguous minute-windows where pm25 is projected below the threshold."""
    windows: List[Dict[str, float]] = []
    start: Optional[int] = None
    for i, v in enumerate(pm25_pred):
        below = v < threshold
        if below and start is None:
            start = i
        elif not below and start is not None:
            windows.append({"start_min": start * STEP_MIN, "end_min": i * STEP_MIN})
            start = None
    if start is not None:
        windows.append({"start_min": start * STEP_MIN,
                        "end_min": len(pm25_pred) * STEP_MIN})
    return windows


def build_forecast(buf, threshold: float, horizon_min: int = 30) -> Dict:
    """Full forecast payload fields (minus contract envelope)."""
    preds = forecast_series(buf, horizon_min)
    return {
        "horizon_min": horizon_min,
        "predictions": preds,
        "threshold_breach_min": threshold_breach_min(preds["pm25"], threshold),
        "safe_windows": safe_windows(preds["pm25"], threshold),
    }
