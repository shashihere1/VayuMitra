"""Pydantic v2 models mirroring every message type in the JSON Schema.

These are convenience builders/serializers.  The JSON Schema in
``schema/messages.schema.json`` remains the source of truth; ``validate.py``
checks payloads against it.  Each model's ``.to_payload()`` returns a plain dict
ready to publish, and ``.now_iso()`` stamps a UTC ``ts`` in RFC-3339 form.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


def now_iso() -> str:
    """UTC timestamp in RFC-3339 / ISO-8601 with a trailing 'Z'."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class _Base(BaseModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    ts: str = Field(default_factory=now_iso)

    model_config = {"extra": "forbid"}

    def to_payload(self) -> dict:
        """JSON-serializable dict with None values preserved (contract allows nulls)."""
        return self.model_dump(mode="json")


# --------------------------------------------------------------------------- #
class SensorReading(_Base):
    msg_type: Literal["SensorReading"] = "SensorReading"
    device_id: str
    pm1_0: Optional[float] = None
    pm25: float
    pm10: Optional[float] = None
    temperature: float
    humidity: float = Field(ge=0, le=100)
    pressure: Optional[float] = None
    voc_index: Optional[float] = None
    source: Literal["bme680+gp2y10", "bme690+gp2y10", "sim"] = "sim"


class Profile(_Base):
    msg_type: Literal["Profile"] = "Profile"
    user_id: str
    severity: Literal["mild", "moderate", "severe"] = "moderate"
    triggers: list[str] = Field(default_factory=list)
    aqi_tolerance: float = Field(default=100.0, ge=0, le=500)
    humidity_threshold: Optional[float] = Field(default=70.0, ge=0, le=100)
    medication: Optional[str] = None


class RiskAssessment(_Base):
    msg_type: Literal["RiskAssessment"] = "RiskAssessment"
    user_id: str
    device_id: Optional[str] = None
    risk_score: float = Field(ge=0, le=100)
    risk_level: Literal["low", "moderate", "high", "critical"]
    engine: Literal["npu", "cpu", "heuristic"]
    inference_ms: Optional[float] = None
    top_factors: list[str] = Field(default_factory=list)
    advisory: Optional[str] = None
    advisory_source: Optional[Literal["llm", "template"]] = None


class Predictions(BaseModel):
    pm25: list[float] = Field(default_factory=list)
    humidity: list[float] = Field(default_factory=list)
    model_config = {"extra": "allow"}


class SafeWindow(BaseModel):
    start_min: float
    end_min: float
    model_config = {"extra": "allow"}


class ForecastUpdate(_Base):
    msg_type: Literal["ForecastUpdate"] = "ForecastUpdate"
    user_id: str
    horizon_min: float = 30
    predictions: Predictions = Field(default_factory=Predictions)
    threshold_breach_min: Optional[float] = None
    safe_windows: list[SafeWindow] = Field(default_factory=list)


class SafeZone(BaseModel):
    name: str
    lat: float
    lon: float
    distance_m: float
    model_config = {"extra": "allow"}


class EmergencyAlert(_Base):
    msg_type: Literal["EmergencyAlert"] = "EmergencyAlert"
    alert_id: str
    user_id: str
    risk_score: float = Field(ge=0, le=100)
    reason: str
    recommended_action: Optional[str] = None
    safe_zone: Optional[SafeZone] = None


class EmergencyAck(_Base):
    msg_type: Literal["EmergencyAck"] = "EmergencyAck"
    alert_id: str
    user_id: Optional[str] = None
    source: Literal["mobile", "knob"]


class DeviceCommand(_Base):
    msg_type: Literal["DeviceCommand"] = "DeviceCommand"
    action: Literal["alarm_on", "alarm_off", "led", "clear"]
    led_color: Optional[Literal["green", "amber", "red", "off"]] = None
    alert_id: Optional[str] = None


class DeviceStatus(_Base):
    msg_type: Literal["DeviceStatus"] = "DeviceStatus"
    device_id: Optional[str] = None
    online: bool = True
    role: Literal["uno_q", "mobile", "ai_pc", "cloud"]


class CloudZone(BaseModel):
    name: str
    lat: float
    lon: float
    aqi: float = 0
    level: str = "low"
    model_config = {"extra": "allow"}


class CloudZoneUpdate(_Base):
    msg_type: Literal["CloudZoneUpdate"] = "CloudZoneUpdate"
    zones: list[CloudZone] = Field(default_factory=list)
    outlook_48h: Optional[str] = None
    source: Literal["cloud_ai_100", "template"] = "template"


# Registry for dynamic construction from a raw payload dict.
MODEL_BY_TYPE: dict[str, type[_Base]] = {
    "SensorReading": SensorReading,
    "Profile": Profile,
    "RiskAssessment": RiskAssessment,
    "ForecastUpdate": ForecastUpdate,
    "EmergencyAlert": EmergencyAlert,
    "EmergencyAck": EmergencyAck,
    "DeviceCommand": DeviceCommand,
    "DeviceStatus": DeviceStatus,
    "CloudZoneUpdate": CloudZoneUpdate,
}


def parse(payload: dict) -> _Base:
    """Build the matching pydantic model from a raw payload (uses ``msg_type``)."""
    mt = payload.get("msg_type")
    model = MODEL_BY_TYPE.get(mt)
    if model is None:
        raise ValueError(f"unknown msg_type: {mt!r}")
    return model.model_validate(payload)
