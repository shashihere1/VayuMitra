package com.vayumitra.data

/** MQTT topic builders — mirror packages/contract/topics.py. */
object Topics {
    const val PREFIX = "vayumitra"

    fun telemetry(deviceId: String) = "$PREFIX/telemetry/$deviceId"
    fun status(deviceId: String) = "$PREFIX/status/$deviceId"
    fun profile(userId: String) = "$PREFIX/profile/$userId"
    fun risk(userId: String) = "$PREFIX/risk/$userId"
    fun forecast(userId: String) = "$PREFIX/forecast/$userId"
    fun emergencyAlert() = "$PREFIX/emergency/alert"
    fun emergencyAck() = "$PREFIX/emergency/ack"
    fun deviceCmd(deviceId: String) = "$PREFIX/device/$deviceId/cmd"
    fun cloudZones() = "$PREFIX/cloud/zones"
}
