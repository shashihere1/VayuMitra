"""Mock Bridge — stands in for the Arduino App Lab Bridge so ``main.py`` runs on
any laptop with ``--mock``.

Produces synthetic BME values + a synthetic GP2Y1010 ``pm25`` with an
auto-triggered spike every ~40 s (and honors a keyboard 's' if run interactively
in a real terminal).  ``set_alarm`` / ``set_led`` print what the hardware would
do; ``poll_knob`` returns True once shortly after a spike (simulating a physical
ack) so the closed loop can be demoed without a board.
"""
from __future__ import annotations

import math
import random
import time


class MockBridge:
    def __init__(self, spike_period_s: float = 40.0):
        self._t0 = time.time()
        self._rng = random.Random(7)
        self._spike_period = spike_period_s
        self._alarm = False
        self._led = "green"
        self._knob_armed = False
        self._last_spike_center = None

    # --- sensing --------------------------------------------------------- #
    def read_sensors(self) -> dict:
        t = time.time() - self._t0
        # baselines with gentle noise
        temperature = 27.0 + 2.0 * math.sin(t / 30.0) + self._rng.uniform(-0.2, 0.2)
        humidity = 52.0 + 6.0 * math.sin(t / 45.0) + self._rng.uniform(-0.5, 0.5)
        pressure = 1008.0 + self._rng.uniform(-0.5, 0.5)
        pm25 = 18.0 + self._rng.uniform(-3, 3)
        voc = 40.0 + self._rng.uniform(-5, 5)

        # periodic spike: a bell around each period center, ~10 s wide
        phase = t % self._spike_period
        center = self._spike_period - 12.0
        if abs(phase - center) < 6.0:
            bell = math.exp(-((phase - center) ** 2) / 8.0)
            pm25 += 300.0 * bell
            voc += 380.0 * bell
            humidity = min(88.0, humidity + 20.0 * bell)
            self._last_spike_center = t
            self._knob_armed = True

        return {
            "pm25": round(max(0.0, pm25), 1),
            "temperature": round(temperature, 2),
            "humidity": round(min(100.0, max(0.0, humidity)), 1),
            "pressure": round(pressure, 1),
            "voc_index": round(min(500.0, max(0.0, voc)), 1),
        }

    # --- actuation (print what the board would do) ----------------------- #
    def set_alarm(self, on: bool) -> None:
        if on != self._alarm:
            print(f"[MOCK HW] BUZZER {'ON  🔊' if on else 'OFF'}")
        self._alarm = on

    def set_led(self, color: str) -> None:
        if color != self._led:
            icon = {"green": "🟢", "amber": "🟡", "red": "🔴", "off": "⚫"}.get(color, "?")
            print(f"[MOCK HW] LED -> {color} {icon}")
        self._led = color

    def poll_knob(self) -> bool:
        """Simulate a physical ack: fire once ~8 s after a spike began."""
        if self._knob_armed and self._last_spike_center is not None:
            if (time.time() - self._t0) - self._last_spike_center > 8.0:
                self._knob_armed = False
                print("[MOCK HW] KNOB button pressed (physical ack)")
                return True
        return False
