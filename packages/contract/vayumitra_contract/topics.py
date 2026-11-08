"""MQTT topic helpers for VayuMitra.

Every topic is namespaced under ``vayumitra/``.  The functions below are the
*only* place topic strings are constructed, so all six lanes agree on the wire
format without importing each other's code.

See ``docs/MQTT_CONTRACT.md`` for the full table (publisher -> subscriber, QoS,
retained flag).
"""
from __future__ import annotations

PREFIX = "vayumitra"

# QoS is 1 for every topic in the contract.
QOS = 1


def telemetry(device_id: str) -> str:
    """UNO Q -> orchestrator, dashboard.  SensorReading.  QoS 1, not retained."""
    return f"{PREFIX}/telemetry/{device_id}"


def status(device_id: str) -> str:
    """any -> all (also used as the LWT topic).  DeviceStatus.  QoS 1, retained."""
    return f"{PREFIX}/status/{device_id}"


def profile(user_id: str) -> str:
    """phone -> orchestrator.  Profile.  QoS 1, retained."""
    return f"{PREFIX}/profile/{user_id}"


def risk(user_id: str) -> str:
    """orchestrator -> phone, dashboard.  RiskAssessment.  QoS 1, retained."""
    return f"{PREFIX}/risk/{user_id}"


def forecast(user_id: str) -> str:
    """orchestrator -> phone, dashboard.  ForecastUpdate.  QoS 1, not retained."""
    return f"{PREFIX}/forecast/{user_id}"


def emergency_alert() -> str:
    """orchestrator -> phone, dashboard, cloud.  EmergencyAlert.  QoS 1, not retained."""
    return f"{PREFIX}/emergency/alert"


def emergency_ack() -> str:
    """phone/knob -> orchestrator.  EmergencyAck.  QoS 1, not retained."""
    return f"{PREFIX}/emergency/ack"


def device_cmd(device_id: str) -> str:
    """orchestrator -> UNO Q.  DeviceCommand.  QoS 1, not retained."""
    return f"{PREFIX}/device/{device_id}/cmd"


def cloud_zones() -> str:
    """cloud -> phone, dashboard.  CloudZoneUpdate.  QoS 1, retained."""
    return f"{PREFIX}/cloud/zones"


# --- wildcard subscriptions (used by the orchestrator / dashboard) -----------

def all_telemetry() -> str:
    return f"{PREFIX}/telemetry/+"


def all_status() -> str:
    return f"{PREFIX}/status/+"


def all_profiles() -> str:
    return f"{PREFIX}/profile/+"


def all_risk() -> str:
    return f"{PREFIX}/risk/+"


def all_forecast() -> str:
    return f"{PREFIX}/forecast/+"


def all_device_cmd() -> str:
    return f"{PREFIX}/device/+/cmd"


def device_id_from_telemetry(topic: str) -> str:
    """Extract ``<device_id>`` from ``vayumitra/telemetry/<device_id>``."""
    return topic.rsplit("/", 1)[-1]


def user_id_from_topic(topic: str) -> str:
    """Extract the trailing id segment (works for risk/forecast/profile)."""
    return topic.rsplit("/", 1)[-1]


def msg_type_for_topic(topic: str) -> str | None:
    """Best-effort mapping of a concrete topic to its message type.

    Used by the MQTT dispatcher to route by topic when the payload's
    ``msg_type`` is missing or when subscribing to wildcards.
    """
    parts = topic.split("/")
    if len(parts) < 2:
        return None
    kind = parts[1]
    mapping = {
        "telemetry": "SensorReading",
        "status": "DeviceStatus",
        "profile": "Profile",
        "risk": "RiskAssessment",
        "forecast": "ForecastUpdate",
    }
    if kind == "emergency":
        return "EmergencyAlert" if topic.endswith("/alert") else "EmergencyAck"
    if kind == "device":
        return "DeviceCommand"
    if kind == "cloud":
        return "CloudZoneUpdate"
    return mapping.get(kind)
