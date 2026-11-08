"""Synthetic telemetry generator for ``--sim`` and the ``/trigger_spike`` demo
backup.  Feeds ``SensorReading`` dicts through the *same* pipeline as real
hardware, so the whole stack demos on a laptop with no board.

A gentle random walk around clean-air baselines, with a scriptable spike that
ramps pm25 (and VOC) up and back down — driving WATCH -> EMERGENCY -> clear.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from vayumitra_contract.models import SensorReading


@dataclass
class Simulator:
    device_id: str
    source: str = "sim"
    # baselines
    pm25: float = 18.0
    temperature: float = 27.0
    humidity: float = 52.0
    pressure: float = 1008.0
    voc_index: float = 40.0

    _t: int = 0
    _spike_ttl: int = 0
    _spike_peak_pm25: float = 260.0
    _spike_peak_voc: float = 380.0
    _rng: random.Random = field(default_factory=lambda: random.Random(1234))

    def trigger_spike(self, steps: int = 14) -> None:
        """Queue a pollution spike lasting ~``steps`` readings."""
        self._spike_ttl = steps

    def _walk(self, value: float, lo: float, hi: float, step: float) -> float:
        value += self._rng.uniform(-step, step)
        return max(lo, min(hi, value))

    def next_reading(self) -> SensorReading:
        self._t += 1
        # gentle diurnal wander on the baselines
        self.temperature = self._walk(self.temperature, 20, 34, 0.15)
        self.humidity = self._walk(self.humidity, 35, 70, 0.6)
        self.pressure = self._walk(self.pressure, 1000, 1015, 0.2)

        if self._spike_ttl > 0:
            # bell-shaped ramp up then down across the spike window
            phase = 1.0 - abs((self._spike_ttl - 7) / 7.0)  # 0..1..0
            phase = max(0.0, phase)
            target_pm = 20 + self._spike_peak_pm25 * phase
            target_voc = 40 + self._spike_peak_voc * phase
            self.pm25 += (target_pm - self.pm25) * 0.6
            self.voc_index += (target_voc - self.voc_index) * 0.6
            self.humidity = min(85.0, self.humidity + 6 * phase)
            self._spike_ttl -= 1
        else:
            self.pm25 = self._walk(self.pm25, 8, 35, 1.5)
            self.voc_index = self._walk(self.voc_index, 20, 70, 3.0)

        return SensorReading(
            device_id=self.device_id,
            pm25=round(self.pm25, 1),
            pm10=None,
            pm1_0=None,
            temperature=round(self.temperature, 2),
            humidity=round(self.humidity, 1),
            pressure=round(self.pressure, 1),
            voc_index=round(self.voc_index, 1),
            source=self.source,
        )
