"""Contract validation: each message type accepts a valid payload and rejects
an invalid one."""
from __future__ import annotations

import pytest

from vayumitra_contract import models, topics
from vayumitra_contract.validate import ValidationError, is_valid, validate


def test_topics_shape():
    assert topics.telemetry("unoq-01") == "vayumitra/telemetry/unoq-01"
    assert topics.risk("demo-user") == "vayumitra/risk/demo-user"
    assert topics.emergency_alert() == "vayumitra/emergency/alert"
    assert topics.msg_type_for_topic("vayumitra/telemetry/x") == "SensorReading"
    assert topics.msg_type_for_topic("vayumitra/emergency/ack") == "EmergencyAck"
    assert topics.device_cmd("d1") == "vayumitra/device/d1/cmd"


def test_sensorreading_valid_and_invalid():
    good = models.SensorReading(device_id="unoq-01", pm25=42.0, temperature=28.0,
                                humidity=55.0, source="sim").to_payload()
    validate(good, "SensorReading")            # no raise
    assert is_valid(good, "SensorReading")

    bad = dict(good)
    bad["humidity"] = 150                       # >100 violates schema
    with pytest.raises(ValidationError):
        validate(bad, "SensorReading")

    missing = dict(good)
    del missing["pm25"]                         # required
    assert not is_valid(missing, "SensorReading")


def test_all_models_roundtrip_validate():
    """Every pydantic model produces a payload that validates against its schema."""
    samples = [
        ("SensorReading", models.SensorReading(device_id="d", pm25=10, temperature=25,
                                               humidity=50, source="bme680+gp2y10")),
        ("Profile", models.Profile(user_id="u", severity="severe", triggers=["smoke"],
                                   aqi_tolerance=80, humidity_threshold=65,
                                   medication="albuterol")),
        ("RiskAssessment", models.RiskAssessment(user_id="u", risk_score=88.0,
                                                 risk_level="critical", engine="npu",
                                                 inference_ms=1.2, top_factors=["high PM2.5"],
                                                 advisory="Move indoors.", advisory_source="llm")),
        ("ForecastUpdate", models.ForecastUpdate(user_id="u", horizon_min=30,
                                                 predictions=models.Predictions(pm25=[1, 2],
                                                                                 humidity=[3, 4]),
                                                 threshold_breach_min=12,
                                                 safe_windows=[models.SafeWindow(start_min=0, end_min=5)])),
        ("EmergencyAlert", models.EmergencyAlert(alert_id="a1", user_id="u", risk_score=90,
                                                 reason="pm2.5 critical",
                                                 recommended_action="move",
                                                 safe_zone=models.SafeZone(name="Park", lat=1.0,
                                                                           lon=2.0, distance_m=100))),
        ("EmergencyAck", models.EmergencyAck(alert_id="a1", source="mobile")),
        ("DeviceCommand", models.DeviceCommand(action="alarm_on", led_color="red", alert_id="a1")),
        ("DeviceStatus", models.DeviceStatus(device_id="d", online=True, role="uno_q")),
        ("CloudZoneUpdate", models.CloudZoneUpdate(zones=[models.CloudZone(name="Z", lat=1, lon=2,
                                                                           aqi=120, level="high")],
                                                   outlook_48h="worsening", source="template")),
    ]
    for msg_type, model in samples:
        payload = model.to_payload()
        validate(payload, msg_type)
        assert payload["schema_version"] == 1
        assert payload["msg_type"] == msg_type
        assert "ts" in payload


def test_enum_rejection():
    bad = models.SensorReading(device_id="d", pm25=1, temperature=1, humidity=1).to_payload()
    bad["source"] = "not-a-source"
    with pytest.raises(ValidationError):
        validate(bad, "SensorReading")


def test_parse_dispatch():
    p = models.RiskAssessment(user_id="u", risk_score=1, risk_level="low",
                              engine="cpu").to_payload()
    obj = models.parse(p)
    assert isinstance(obj, models.RiskAssessment)
    with pytest.raises(ValueError):
        models.parse({"msg_type": "Nope"})
