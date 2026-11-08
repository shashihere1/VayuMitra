"""VayuMitra contract package — the single cross-lane coupling.

Exposes:
  * ``topics``  — MQTT topic builders
  * ``models``  — pydantic v2 models + ``parse()`` + ``now_iso()``
  * ``validate``— JSON-Schema validation (``validate``, ``is_valid``, ``iter_errors``)
"""
from __future__ import annotations

from . import models, topics, validate
from .models import (
    SCHEMA_VERSION,
    CloudZoneUpdate,
    DeviceCommand,
    DeviceStatus,
    EmergencyAck,
    EmergencyAlert,
    ForecastUpdate,
    Profile,
    RiskAssessment,
    SensorReading,
    now_iso,
    parse,
)

__version__ = "1.0.0"

__all__ = [
    "topics",
    "models",
    "validate",
    "SCHEMA_VERSION",
    "now_iso",
    "parse",
    "SensorReading",
    "Profile",
    "RiskAssessment",
    "ForecastUpdate",
    "EmergencyAlert",
    "EmergencyAck",
    "DeviceCommand",
    "DeviceStatus",
    "CloudZoneUpdate",
]
