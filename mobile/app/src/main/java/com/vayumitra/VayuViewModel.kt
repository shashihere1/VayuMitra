package com.vayumitra

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.vayumitra.data.MqttService
import com.vayumitra.data.RiskModel
import com.vayumitra.model.EmergencyAlert
import com.vayumitra.model.ForecastUpdate
import com.vayumitra.model.Profile
import com.vayumitra.model.RiskAssessment
import com.vayumitra.model.SensorReading
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class UiState(
    val connected: Boolean = false,
    val profile: Profile = Profile(user_id = BuildConfig.USER_ID),
    val latestReading: SensorReading? = null,
    val risk: RiskAssessment? = null,
    val forecast: ForecastUpdate? = null,
    val activeAlert: EmergencyAlert? = null,
    val onDeviceEngine: String = "heuristic",
    val usingOnDeviceRisk: Boolean = false,
)

/**
 * Ties MQTT + the on-device model to a single [UiState] StateFlow.
 *
 * When connected, the authoritative AI-PC [RiskAssessment] drives the gauge.
 * If risk updates go stale (broker/AI-PC dropped or Wi-Fi off), a watchdog
 * falls back to the on-device model computed from the last cached reading —
 * so the phone always shows a risk value.
 */
class VayuViewModel(app: Application) : AndroidViewModel(app) {

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    private val riskModel = RiskModel(app)
    private var lastRiskAtMs: Long = 0
    private val userId = BuildConfig.USER_ID

    private val mqtt = MqttService(
        host = BuildConfig.MQTT_HOST,
        port = BuildConfig.MQTT_PORT,
        userId = userId,
        onRisk = { r -> lastRiskAtMs = System.currentTimeMillis()
            _ui.update { it.copy(risk = r, usingOnDeviceRisk = false) } },
        onForecast = { f -> _ui.update { it.copy(forecast = f) } },
        onAlert = { a -> _ui.update { it.copy(activeAlert = a) } },
        onReading = { s -> _ui.update { it.copy(latestReading = s) } },
        onConnectionChange = { c -> _ui.update { it.copy(connected = c) } },
    )

    init {
        _ui.update { it.copy(onDeviceEngine = riskModel.engine) }
        mqtt.connect()
        startOfflineWatchdog()
    }

    /** Every 3 s, if no fresh AI-PC risk arrived, compute locally from last reading. */
    private fun startOfflineWatchdog() {
        viewModelScope.launch {
            while (true) {
                delay(3000)
                val stale = System.currentTimeMillis() - lastRiskAtMs > 6000
                val reading = _ui.value.latestReading
                if (stale && reading != null) {
                    val (score, factors) = riskModel.compute(reading, _ui.value.profile)
                    val local = RiskAssessment(
                        user_id = userId,
                        risk_score = score,
                        risk_level = RiskModel.levelFor(score),
                        engine = riskModel.engine,
                        top_factors = factors,
                        advisory = "On-device estimate (offline).",
                        advisory_source = "template",
                    )
                    _ui.update { it.copy(risk = local, usingOnDeviceRisk = true) }
                }
            }
        }
    }

    fun saveProfile(profile: Profile) {
        _ui.update { it.copy(profile = profile) }
        mqtt.publishProfile(profile)
    }

    fun acknowledge() {
        _ui.value.activeAlert?.let { mqtt.publishAck(it.alert_id) }
        _ui.update { it.copy(activeAlert = null) }
    }

    fun dismissAlert() {
        _ui.update { it.copy(activeAlert = null) }
    }

    override fun onCleared() {
        mqtt.disconnect()
        riskModel.close()
        super.onCleared()
    }
}
