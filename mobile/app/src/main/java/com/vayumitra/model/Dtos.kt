package com.vayumitra.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * DTOs mirroring docs/MQTT_CONTRACT.md. `@SerialName` + default values keep
 * (de)serialization tolerant of nulls/omissions. `ignoreUnknownKeys` is set on
 * the Json instance in MqttService.
 */

@Serializable
data class SensorReading(
    val schema_version: Int = 1,
    val msg_type: String = "SensorReading",
    val ts: String = "",
    val device_id: String = "",
    val pm1_0: Double? = null,
    val pm25: Double = 0.0,
    val pm10: Double? = null,
    val temperature: Double = 0.0,
    val humidity: Double = 0.0,
    val pressure: Double? = null,
    val voc_index: Double? = null,
    val source: String = "sim"
)

@Serializable
data class Profile(
    val schema_version: Int = 1,
    val msg_type: String = "Profile",
    val ts: String = "",
    val user_id: String = "",
    val severity: String = "moderate",
    val triggers: List<String> = emptyList(),
    val aqi_tolerance: Double = 100.0,
    val humidity_threshold: Double? = 70.0,
    val medication: String? = null
)

@Serializable
data class RiskAssessment(
    val schema_version: Int = 1,
    val msg_type: String = "RiskAssessment",
    val ts: String = "",
    val user_id: String = "",
    val device_id: String? = null,
    val risk_score: Double = 0.0,
    val risk_level: String = "low",
    val engine: String = "heuristic",
    val inference_ms: Double? = null,
    val top_factors: List<String> = emptyList(),
    val advisory: String? = null,
    val advisory_source: String? = null
)

@Serializable
data class Predictions(
    val pm25: List<Double> = emptyList(),
    val humidity: List<Double> = emptyList()
)

@Serializable
data class SafeWindow(
    val start_min: Double = 0.0,
    val end_min: Double = 0.0
)

@Serializable
data class ForecastUpdate(
    val schema_version: Int = 1,
    val msg_type: String = "ForecastUpdate",
    val ts: String = "",
    val user_id: String = "",
    val horizon_min: Double = 30.0,
    val predictions: Predictions = Predictions(),
    val threshold_breach_min: Double? = null,
    val safe_windows: List<SafeWindow> = emptyList()
)

@Serializable
data class SafeZone(
    val name: String = "",
    val lat: Double = 0.0,
    val lon: Double = 0.0,
    val distance_m: Double = 0.0
)

@Serializable
data class EmergencyAlert(
    val schema_version: Int = 1,
    val msg_type: String = "EmergencyAlert",
    val ts: String = "",
    val alert_id: String = "",
    val user_id: String = "",
    val risk_score: Double = 0.0,
    val reason: String = "",
    val recommended_action: String? = null,
    val safe_zone: SafeZone? = null
)

@Serializable
data class EmergencyAck(
    val schema_version: Int = 1,
    val msg_type: String = "EmergencyAck",
    val ts: String = "",
    val alert_id: String = "",
    val user_id: String? = null,
    val source: String = "mobile"
)

@Serializable
data class DeviceStatus(
    val schema_version: Int = 1,
    val msg_type: String = "DeviceStatus",
    val ts: String = "",
    val device_id: String? = null,
    val online: Boolean = true,
    val role: String = "mobile"
)
