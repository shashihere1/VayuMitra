"""Bounded 0-100 Asthma Risk heuristic.

This single function is used three ways:
  1. **Label generator** for the synthetic training set (``gen_data.py``).
  2. **Runtime fallback** when the NPU/CPU ONNX model is unavailable
     (``inference.py``).
  3. **Explainer** — it always returns per-term contributions, so ``top_factors``
     can explain *any* score (even one produced by the neural net).

The score is a weighted sum of normalized drivers — PM2.5 dominant — scaled by
the user's asthma severity and personal sensitivity, plus spike penalties on
positive rates of change.  Bounded to [0, 100].

``FEATURE_ORDER`` is the canonical feature vector shared with ``features.py``
and the trained model.  Do not reorder it without retraining.
"""
from __future__ import annotations

from typing import Dict, Sequence, Tuple

FEATURE_ORDER = [
    "pm25",
    "pm10",
    "temperature",
    "humidity",
    "voc_index",
    "pressure",
    "pm25_rate_per_min",
    "humidity_rate_per_min",
    "temp_rate_per_min",
    "severity_ordinal",       # mild=0, moderate=1, severe=2
    "personal_sensitivity",   # 0..1  (= clamp(1 - aqi_tolerance/150, 0, 1))
]

N_FEATURES = len(FEATURE_ORDER)

SEVERITY_ORDINAL = {"mild": 0, "moderate": 1, "severe": 2}

# Human-friendly labels for the contribution terms (used in top_factors).
_FACTOR_LABELS = {
    "pm25": "high PM2.5",
    "pm25_spike": "rapid PM2.5 rise",
    "humidity": "humidity out of comfort range",
    "voc": "elevated VOC / gas",
    "temp_drop": "rapid temperature drop",
    "pressure": "low / falling pressure",
    "humidity_spike": "rapid humidity rise",
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _to_dict(features: Sequence[float] | Dict[str, float]) -> Dict[str, float]:
    if isinstance(features, dict):
        return {k: float(features.get(k, 0.0) or 0.0) for k in FEATURE_ORDER}
    if len(features) != N_FEATURES:
        raise ValueError(f"expected {N_FEATURES} features, got {len(features)}")
    return {k: float(v or 0.0) for k, v in zip(FEATURE_ORDER, features)}


def heuristic(features: Sequence[float] | Dict[str, float]) -> Tuple[float, Dict[str, float]]:
    """Return ``(score, contributions)``.

    ``score`` is in [0, 100].  ``contributions`` maps a factor key to its
    (already personal-scaled) points, so ``sum(contributions.values())`` ~ score
    before clamping.
    """
    f = _to_dict(features)

    pm25 = f["pm25"]
    humidity = f["humidity"]
    voc = f["voc_index"]
    pressure = f["pressure"]
    temp_rate = f["temp_rate_per_min"]
    pm25_rate = f["pm25_rate_per_min"]
    hum_rate = f["humidity_rate_per_min"]
    severity = int(_clamp(f["severity_ordinal"], 0, 2))
    sensitivity = _clamp(f["personal_sensitivity"], 0.0, 1.0)

    c: Dict[str, float] = {}

    # PM2.5 — dominant driver. Saturates around 200 ug/m3-equiv.
    c["pm25"] = 60.0 * _clamp(pm25 / 200.0, 0.0, 1.0)

    # Humidity discomfort: high (>60%) worse than low (<30%).
    if humidity > 60:
        c["humidity"] = 12.0 * _clamp((humidity - 60.0) / 35.0, 0.0, 1.0)
    elif humidity < 30:
        c["humidity"] = 8.0 * _clamp((30.0 - humidity) / 30.0, 0.0, 1.0)
    else:
        c["humidity"] = 0.0

    # VOC / gas index (0..500).
    c["voc"] = 15.0 * _clamp(voc / 500.0, 0.0, 1.0)

    # Rapid temperature drop (cold-air trigger). Only negative rates penalize.
    c["temp_drop"] = 8.0 * _clamp(-temp_rate / 2.0, 0.0, 1.0)

    # Low / falling pressure (optional). Below ~1010 hPa contributes.
    if pressure:
        c["pressure"] = 5.0 * _clamp((1010.0 - pressure) / 30.0, 0.0, 1.0)
    else:
        c["pressure"] = 0.0

    # Spike penalties on positive rates of change.
    c["pm25_spike"] = 10.0 * _clamp(pm25_rate / 20.0, 0.0, 1.0)
    c["humidity_spike"] = 5.0 * _clamp(hum_rate / 10.0, 0.0, 1.0)

    raw = sum(c.values())

    # Personal scaling: severity multiplier + sensitivity boost.
    sev_mult = {0: 0.85, 1: 1.0, 2: 1.2}[severity]
    sens_mult = 1.0 + 0.5 * sensitivity            # 1.0 .. 1.5
    scale = sev_mult * sens_mult

    scaled = {k: v * scale for k, v in c.items()}
    score = _clamp(raw * scale, 0.0, 100.0)
    return score, scaled


def level_for(score: float) -> str:
    """Map a 0-100 score to a risk level (contract enum)."""
    if score < 25:
        return "low"
    if score < 50:
        return "moderate"
    if score < 75:
        return "high"
    return "critical"


def top_factors(contributions: Dict[str, float], n: int = 3) -> list[str]:
    """Return up to ``n`` human-readable factor labels, biggest first."""
    ranked = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)
    out: list[str] = []
    for key, val in ranked:
        if val <= 0.5:  # ignore negligible terms
            continue
        out.append(_FACTOR_LABELS.get(key, key))
        if len(out) >= n:
            break
    return out or ["nominal conditions"]
