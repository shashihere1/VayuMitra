"""THE HERO: per-user emergency cascade state machine.

``NORMAL -> WATCH -> EMERGENCY -> ACKED`` with **hysteresis + dwell**.  One event
(risk crossing critical) produces four coordinated device behaviors via the
actions this machine emits; the orchestrator turns them into MQTT messages.

The machine is **pure and clock-injected**: every method takes ``now`` (seconds)
and *returns* a list of :class:`Action` descriptors instead of doing I/O, so it
is deterministically unit-testable with a fake clock (see ``tests/test_cascade.py``).

Transition table (thresholds from config; dwell counts are consecutive readings):

| From              | Event                          | To        | Actions                          |
|-------------------|--------------------------------|-----------|----------------------------------|
| NORMAL            | score >= warning x2            | WATCH     | LED amber                        |
| WATCH             | score >= critical x2           | EMERGENCY | FIRE CASCADE (alert+alarm+red)   |
| WATCH             | score < warning x3             | NORMAL    | LED green                        |
| EMERGENCY         | EmergencyAck                   | ACKED     | alarm off, LED amber, stop realert|
| EMERGENCY         | no ack for 20 s                | EMERGENCY | re-publish alert + re-buzz       |
| ACKED / EMERGENCY | score < clear x3               | NORMAL    | LED green + DeviceCommand{clear}  |
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

RE_ALERT_SECONDS = 20.0

# dwell requirements (consecutive readings)
DWELL_WATCH = 2      # NORMAL -> WATCH
DWELL_EMERGENCY = 2  # WATCH -> EMERGENCY
DWELL_DEESCALATE = 3 # back-off transitions


class State(str, Enum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    EMERGENCY = "EMERGENCY"
    ACKED = "ACKED"


@dataclass
class Action:
    """A device behavior the orchestrator should perform."""
    kind: str                      # "led" | "alarm" | "alert" | "clear" | "ack_latency"
    led_color: Optional[str] = None
    alarm_on: Optional[bool] = None
    alert_id: Optional[str] = None
    reason: Optional[str] = None
    is_realert: bool = False
    latency_s: Optional[float] = None


@dataclass
class CascadeMachine:
    user_id: str
    critical: float = 75.0
    warning: float = 50.0
    clear: float = 60.0

    state: State = State.NORMAL
    alert_id: Optional[str] = None
    t_alert: Optional[float] = None
    last_alert_at: Optional[float] = None
    _alert_seq: int = 0

    # dwell counters
    _c_warn: int = 0
    _c_crit: int = 0
    _c_below_warn: int = 0
    _c_below_clear: int = 0

    last_score: float = 0.0
    last_reason: str = ""

    # --- helpers ---------------------------------------------------------- #
    def _new_alert_id(self) -> str:
        self._alert_seq += 1
        return f"{self.user_id}-alert-{self._alert_seq}"

    def _fire(self, now: float, reason: str) -> List[Action]:
        self.alert_id = self._new_alert_id()
        self.t_alert = now
        self.last_alert_at = now
        self.last_reason = reason
        return [
            Action(kind="alert", alert_id=self.alert_id, reason=reason, is_realert=False),
            Action(kind="alarm", alarm_on=True),
            Action(kind="led", led_color="red"),
        ]

    # --- events ----------------------------------------------------------- #
    def on_reading(self, score: float, now: float, reason: str = "") -> List[Action]:
        """Advance the machine on a new risk score. Returns actions to perform."""
        self.last_score = score

        # update dwell counters (hysteresis)
        self._c_warn = self._c_warn + 1 if score >= self.warning else 0
        self._c_crit = self._c_crit + 1 if score >= self.critical else 0
        self._c_below_warn = self._c_below_warn + 1 if score < self.warning else 0
        self._c_below_clear = self._c_below_clear + 1 if score < self.clear else 0

        actions: List[Action] = []

        if self.state is State.NORMAL:
            if self._c_warn >= DWELL_WATCH:
                self.state = State.WATCH
                actions.append(Action(kind="led", led_color="amber"))

        elif self.state is State.WATCH:
            if self._c_crit >= DWELL_EMERGENCY:
                self.state = State.EMERGENCY
                actions.extend(self._fire(now, reason or "risk crossed critical"))
            elif self._c_below_warn >= DWELL_DEESCALATE:
                self.state = State.NORMAL
                actions.append(Action(kind="led", led_color="green"))

        elif self.state is State.EMERGENCY:
            if self._c_below_clear >= DWELL_DEESCALATE:
                actions.extend(self._deescalate())

        elif self.state is State.ACKED:
            if self._c_below_clear >= DWELL_DEESCALATE:
                actions.extend(self._deescalate())

        return actions

    def on_ack(self, alert_id: Optional[str], now: float) -> List[Action]:
        """Handle an EmergencyAck. Only valid while EMERGENCY; ignores stale ids."""
        if self.state is not State.EMERGENCY:
            return []
        if alert_id is not None and self.alert_id is not None and alert_id != self.alert_id:
            return []  # stale / mismatched ack
        self.state = State.ACKED
        latency = None if self.t_alert is None else max(0.0, now - self.t_alert)
        return [
            Action(kind="alarm", alarm_on=False),
            Action(kind="led", led_color="amber"),
            Action(kind="ack_latency", latency_s=latency),
        ]

    def tick(self, now: float) -> List[Action]:
        """Periodic timer: re-alert if EMERGENCY and unacked for RE_ALERT_SECONDS."""
        if self.state is State.EMERGENCY and self.last_alert_at is not None:
            if now - self.last_alert_at >= RE_ALERT_SECONDS:
                self.last_alert_at = now
                return [
                    Action(kind="alert", alert_id=self.alert_id,
                           reason=self.last_reason or "still critical", is_realert=True),
                    Action(kind="alarm", alarm_on=True),
                    Action(kind="led", led_color="red"),
                ]
        return []

    # --- internal --------------------------------------------------------- #
    def _deescalate(self) -> List[Action]:
        self.state = State.NORMAL
        self.alert_id = None
        self.t_alert = None
        self.last_alert_at = None
        return [
            Action(kind="led", led_color="green"),
            Action(kind="clear"),
        ]

    def snapshot(self) -> Dict:
        return {
            "user_id": self.user_id,
            "state": self.state.value,
            "alert_id": self.alert_id,
            "last_score": round(self.last_score, 1),
        }


class CascadeManager:
    """One machine per user."""

    def __init__(self, critical: float, warning: float, clear: float) -> None:
        self.critical = critical
        self.warning = warning
        self.clear = clear
        self._machines: Dict[str, CascadeMachine] = {}

    def machine(self, user_id: str) -> CascadeMachine:
        m = self._machines.get(user_id)
        if m is None:
            m = self._machines[user_id] = CascadeMachine(
                user_id=user_id,
                critical=self.critical,
                warning=self.warning,
                clear=self.clear,
            )
        return m

    def all_snapshots(self) -> List[Dict]:
        return [m.snapshot() for m in self._machines.values()]
