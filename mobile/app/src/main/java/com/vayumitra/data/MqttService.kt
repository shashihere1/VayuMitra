package com.vayumitra.data

import android.util.Log
import com.hivemq.client.mqtt.MqttClient
import com.hivemq.client.mqtt.datatypes.MqttQos
import com.hivemq.client.mqtt.mqtt3.Mqtt3AsyncClient
import com.vayumitra.model.DeviceStatus
import com.vayumitra.model.EmergencyAck
import com.vayumitra.model.EmergencyAlert
import com.vayumitra.model.ForecastUpdate
import com.vayumitra.model.Profile
import com.vayumitra.model.RiskAssessment
import com.vayumitra.model.SensorReading
import kotlinx.serialization.json.Json
import java.nio.charset.StandardCharsets
import java.util.UUID

/**
 * HiveMQ MQTT client pointed at the same local broker as the rest of the system.
 * Subscribes to risk / forecast / emergency for this user; publishes retained
 * Profile + DeviceStatus, and EmergencyAck. Never throws to the caller — all
 * failures are logged so the UI (and the on-device model) keep working offline.
 */
class MqttService(
    private val host: String,
    private val port: Int,
    private val userId: String,
    private val onRisk: (RiskAssessment) -> Unit,
    private val onForecast: (ForecastUpdate) -> Unit,
    private val onAlert: (EmergencyAlert) -> Unit,
    private val onReading: (SensorReading) -> Unit,
    private val onConnectionChange: (Boolean) -> Unit,
) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val clientId = "vayumitra-mobile-${UUID.randomUUID().toString().take(8)}"
    private val statusTopic = Topics.status("mobile-$userId")

    private val client: Mqtt3AsyncClient = MqttClient.builder()
        .useMqttVersion3()
        .identifier(clientId)
        .serverHost(host)
        .serverPort(port)
        .automaticReconnectWithDefaultConfig()
        .addConnectedListener { onConnectionChange(true) }
        .addDisconnectedListener { onConnectionChange(false) }
        .buildAsync()

    fun connect() {
        val lwt = json.encodeToString(
            DeviceStatus.serializer(),
            DeviceStatus(device_id = "mobile-$userId", online = false, role = "mobile")
        )
        client.connectWith()
            .willPublish()
                .topic(statusTopic)
                .qos(MqttQos.AT_LEAST_ONCE)
                .retain(true)
                .payload(lwt.toByteArray(StandardCharsets.UTF_8))
                .applyWillPublish()
            .send()
            .whenComplete { _, ex ->
                if (ex != null) {
                    Log.w(TAG, "connect failed: ${ex.message}")
                } else {
                    subscribeAll()
                    publishStatus(true)
                }
            }
    }

    private fun subscribeAll() {
        subscribe(Topics.risk(userId)) { bytes ->
            runCatching { onRisk(json.decodeFromString(RiskAssessment.serializer(), bytes)) }
        }
        subscribe(Topics.forecast(userId)) { bytes ->
            runCatching { onForecast(json.decodeFromString(ForecastUpdate.serializer(), bytes)) }
        }
        subscribe(Topics.emergencyAlert()) { bytes ->
            runCatching {
                val alert = json.decodeFromString(EmergencyAlert.serializer(), bytes)
                if (alert.user_id == userId) onAlert(alert)
            }
        }
        // cache latest sensor reading so the on-device model can compute risk offline
        subscribe("${Topics.PREFIX}/telemetry/+") { bytes ->
            runCatching { onReading(json.decodeFromString(SensorReading.serializer(), bytes)) }
        }
    }

    private fun subscribe(topic: String, handle: (String) -> Unit) {
        client.subscribeWith()
            .topicFilter(topic)
            .qos(MqttQos.AT_LEAST_ONCE)
            .callback { pub ->
                val payload = String(pub.payloadAsBytes, StandardCharsets.UTF_8)
                handle(payload)
            }
            .send()
            .whenComplete { _, ex ->
                if (ex != null) Log.w(TAG, "subscribe $topic failed: ${ex.message}")
                else Log.i(TAG, "subscribed $topic")
            }
    }

    fun publishProfile(profile: Profile) {
        val payload = json.encodeToString(Profile.serializer(), profile)
        publish(Topics.profile(userId), payload, retain = true)
    }

    fun publishAck(alertId: String) {
        val ack = EmergencyAck(alert_id = alertId, user_id = userId, source = "mobile")
        val payload = json.encodeToString(EmergencyAck.serializer(), ack)
        publish(Topics.emergencyAck(), payload, retain = false)
    }

    private fun publishStatus(online: Boolean) {
        val status = DeviceStatus(device_id = "mobile-$userId", online = online, role = "mobile")
        publish(statusTopic, json.encodeToString(DeviceStatus.serializer(), status), retain = true)
    }

    private fun publish(topic: String, payload: String, retain: Boolean) {
        client.publishWith()
            .topic(topic)
            .qos(MqttQos.AT_LEAST_ONCE)
            .retain(retain)
            .payload(payload.toByteArray(StandardCharsets.UTF_8))
            .send()
            .whenComplete { _, ex -> if (ex != null) Log.w(TAG, "publish $topic failed: ${ex.message}") }
    }

    fun disconnect() {
        publishStatus(false)
        client.disconnect()
    }

    companion object {
        private const val TAG = "VayuMqtt"
    }
}
