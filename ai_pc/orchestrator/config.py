"""Runtime configuration loaded from ``.env`` (via python-dotenv) with sane
defaults so the orchestrator always starts, even with no ``.env`` present.

Import ``CFG`` (a singleton) anywhere in the AI-PC lane.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Load repo-root .env if present. Never fails if missing.
    _root = Path(__file__).resolve().parents[2]
    load_dotenv(_root / ".env")
except Exception:  # dotenv optional; env vars still work
    pass


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    # MQTT
    mqtt_host: str = field(default_factory=lambda: os.getenv("MQTT_HOST", "127.0.0.1"))
    mqtt_port: int = field(default_factory=lambda: _i("MQTT_PORT", 1883))

    # identity
    device_id: str = field(default_factory=lambda: os.getenv("DEVICE_ID", "unoq-01"))
    user_id: str = field(default_factory=lambda: os.getenv("USER_ID", "demo-user"))
    device_lat: float = field(default_factory=lambda: _f("DEVICE_LAT", 19.0760))
    device_lon: float = field(default_factory=lambda: _f("DEVICE_LON", 72.8777))

    # sensors (mirrored from the sketch, for docs/mock)
    bme_variant: str = field(default_factory=lambda: os.getenv("BME_VARIANT", "bme680"))

    # software toggles
    use_npu: bool = field(default_factory=lambda: _b("USE_NPU", True))
    use_foundry: bool = field(default_factory=lambda: _b("USE_FOUNDRY", True))
    foundry_model: str = field(default_factory=lambda: os.getenv("FOUNDRY_MODEL", "phi-4-mini"))

    # cascade thresholds (hysteresis)
    risk_critical: float = field(default_factory=lambda: _f("RISK_CRITICAL", 75))
    risk_warning: float = field(default_factory=lambda: _f("RISK_WARNING", 50))
    risk_clear: float = field(default_factory=lambda: _f("RISK_CLEAR", 60))

    # ports
    api_port: int = field(default_factory=lambda: _i("API_PORT", 8000))
    dashboard_port: int = field(default_factory=lambda: _i("DASHBOARD_PORT", 8501))

    # CLI overrides (set by main.py after arg parse)
    force_no_npu: bool = False
    force_no_foundry: bool = False
    sim: bool = False

    @property
    def npu_enabled(self) -> bool:
        return self.use_npu and not self.force_no_npu

    @property
    def foundry_enabled(self) -> bool:
        return self.use_foundry and not self.force_no_foundry

    @property
    def sensor_source(self) -> str:
        return "sim" if self.sim else f"{self.bme_variant}+gp2y10"

    def banner(self, engine: str, advisory: str) -> str:
        lines = [
            "=" * 60,
            " VayuMitra orchestrator",
            f"   MQTT      : {self.mqtt_host}:{self.mqtt_port}",
            f"   DEVICE    : {self.device_id}   USER: {self.user_id}",
            f"   SENSORS   : {self.bme_variant} + gp2y10 (MCU)"
            + ("   [SIMULATOR]" if self.sim else ""),
            f"   INFERENCE : {engine}",
            f"   ADVISORY  : {advisory}",
            f"   THRESHOLDS: critical={self.risk_critical} "
            f"warning={self.risk_warning} clear={self.risk_clear}",
            "=" * 60,
        ]
        return "\n".join(lines)


CFG = Config()
