"""Cascade state-machine tests with an explicit fake clock."""
from __future__ import annotations

from ai_pc.orchestrator.cascade import RE_ALERT_SECONDS, CascadeMachine, State


def machine():
    return CascadeMachine("u", critical=75, warning=50, clear=60)


def kinds(actions):
    return [a.kind for a in actions]


def test_dwell_required_for_watch_and_emergency():
    m = machine()
    m.on_reading(60, 1)                       # 1x warn -> still NORMAL
    assert m.state is State.NORMAL
    m.on_reading(60, 2)                       # 2x warn -> WATCH
    assert m.state is State.WATCH
    m.on_reading(90, 3)                       # 1x crit -> still WATCH
    assert m.state is State.WATCH
    acts = m.on_reading(90, 4)                # 2x crit -> EMERGENCY, fire
    assert m.state is State.EMERGENCY
    assert "alert" in kinds(acts) and "alarm" in kinds(acts)


def test_ack_moves_to_acked_and_stops_realerts():
    m = machine()
    for t in (1, 2, 3, 4):
        m.on_reading(90, t)
    assert m.state is State.EMERGENCY
    ack = m.on_ack(m.alert_id, 5)
    assert m.state is State.ACKED
    assert any(a.kind == "alarm" and a.alarm_on is False for a in ack)
    # after ack, a re-alert tick must NOT fire
    assert m.tick(5 + RE_ALERT_SECONDS + 1) == []


def test_realert_fires_when_unacked():
    m = machine()
    for t in (1, 2, 3, 4):
        m.on_reading(90, t)
    fired_at = m.last_alert_at                              # actual cascade-fire time
    assert m.tick(fired_at + RE_ALERT_SECONDS - 1) == []   # too soon
    acts = m.tick(fired_at + RE_ALERT_SECONDS + 0.1)       # now
    assert any(a.kind == "alert" and a.is_realert for a in acts)


def test_stale_ack_ignored():
    m = machine()
    for t in (1, 2, 3, 4):
        m.on_reading(90, t)
    assert m.on_ack("some-other-alert", 5) == []
    assert m.state is State.EMERGENCY


def test_hysteresis_prevents_flapping():
    m = machine()
    m.on_reading(60, 1)
    m.on_reading(60, 2)                       # WATCH
    # a single dip below warning must NOT drop back to NORMAL
    m.on_reading(40, 3)
    assert m.state is State.WATCH
    m.on_reading(40, 4)
    m.on_reading(40, 5)                       # 3 consecutive < warning -> NORMAL
    assert m.state is State.NORMAL


def test_clear_returns_to_normal_with_command():
    m = machine()
    for t in (1, 2, 3, 4):
        m.on_reading(90, t)
    m.on_ack(m.alert_id, 5)                   # ACKED
    m.on_reading(40, 6)
    m.on_reading(40, 7)
    acts = m.on_reading(40, 8)                # 3x below clear(60) -> NORMAL
    assert m.state is State.NORMAL
    assert "clear" in kinds(acts)
    assert m.alert_id is None
