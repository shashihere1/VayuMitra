"""Heuristic properties: bounded, monotonic in PM2.5, severity ordering, spikes."""
from __future__ import annotations

from ai_pc.ml.heuristic import FEATURE_ORDER, heuristic, level_for


def _feats(**over):
    base = {k: 0.0 for k in FEATURE_ORDER}
    base.update({"temperature": 25.0, "humidity": 50.0, "pressure": 1008.0,
                 "severity_ordinal": 1.0, "personal_sensitivity": 0.5})
    base.update(over)
    return base


def test_bounded_0_100():
    for pm in (0, 50, 100, 250, 400, 10_000):
        s, _ = heuristic(_feats(pm25=pm, voc_index=500, humidity=95,
                                pm25_rate_per_min=100, severity_ordinal=2,
                                personal_sensitivity=1.0))
        assert 0.0 <= s <= 100.0


def test_monotonic_in_pm25():
    prev = -1.0
    for pm in range(0, 260, 20):
        s, _ = heuristic(_feats(pm25=pm))
        assert s >= prev - 1e-9, f"not monotonic at pm25={pm}"
        prev = s


def test_severe_ge_mild():
    mild = heuristic(_feats(pm25=120, severity_ordinal=0))[0]
    severe = heuristic(_feats(pm25=120, severity_ordinal=2))[0]
    assert severe >= mild


def test_pm_spike_raises_score():
    calm = heuristic(_feats(pm25=80, pm25_rate_per_min=0))[0]
    spiking = heuristic(_feats(pm25=80, pm25_rate_per_min=30))[0]
    assert spiking > calm


def test_levels():
    assert level_for(10) == "low"
    assert level_for(40) == "moderate"
    assert level_for(60) == "high"
    assert level_for(90) == "critical"


def test_contributions_sum_close_to_score():
    s, c = heuristic(_feats(pm25=150, voc_index=200, humidity=80))
    # scaled contributions should sum to roughly the (pre-clamp) score
    assert abs(sum(c.values()) - s) < 1e-6 or s == 100.0


def test_accepts_vector_and_dict():
    vec = [80, 112, 25, 50, 100, 1008, 5, 0, 0, 1, 0.5]
    s_vec, _ = heuristic(vec)
    d = dict(zip(FEATURE_ORDER, vec))
    s_dict, _ = heuristic(d)
    assert abs(s_vec - s_dict) < 1e-9
