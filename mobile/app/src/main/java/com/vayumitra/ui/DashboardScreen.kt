package com.vayumitra.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vayumitra.UiState

private fun levelColor(level: String) = when (level) {
    "low" -> Color(0xFF16A34A)
    "moderate" -> Color(0xFFEAB308)
    "high" -> Color(0xFFF97316)
    "critical" -> Color(0xFFDC2626)
    else -> Color(0xFF6B7280)
}

@Composable
fun DashboardScreen(state: UiState, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("VayuMitra", fontSize = 26.sp, fontWeight = FontWeight.Bold)
        Text(
            (if (state.connected) "● connected to broker" else "○ offline") +
                if (state.usingOnDeviceRisk) "  ·  on-device model" else "",
            color = if (state.connected) Color(0xFF16A34A) else Color(0xFF9CA3AF),
            fontSize = 13.sp
        )

        val risk = state.risk
        val level = risk?.risk_level ?: "low"
        val score = risk?.risk_score ?: 0.0
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(20.dp))
                .background(levelColor(level))
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("%.0f".format(score), fontSize = 72.sp, fontWeight = FontWeight.Black, color = Color.White)
            Text(level.uppercase(), fontSize = 20.sp, color = Color.White, fontWeight = FontWeight.SemiBold)
            Text(
                "engine: ${risk?.engine ?: "—"}" +
                    (risk?.inference_ms?.let { "  ·  %.2f ms".format(it) } ?: ""),
                fontSize = 12.sp, color = Color.White.copy(alpha = 0.85f)
            )
        }

        risk?.advisory?.let {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text("💬 $it", fontSize = 15.sp)
                    if (risk.top_factors.isNotEmpty()) {
                        Text("Top factors: " + risk.top_factors.joinToString(", "),
                            fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }

        val r = state.latestReading
        Text("Live sensors", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Metric("PM2.5", r?.pm25?.let { "%.0f".format(it) } ?: "—", Modifier.weight(1f))
            Metric("VOC", r?.voc_index?.let { "%.0f".format(it) } ?: "—", Modifier.weight(1f))
            Metric("Temp", r?.temperature?.let { "%.1f°".format(it) } ?: "—", Modifier.weight(1f))
            Metric("Humid", r?.humidity?.let { "%.0f%%".format(it) } ?: "—", Modifier.weight(1f))
        }

        state.forecast?.let { f ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text("🔮 Forecast (${f.horizon_min.toInt()} min)", fontWeight = FontWeight.SemiBold)
                    Text(
                        f.threshold_breach_min?.let { "PM2.5 threshold breach in ~${it.toInt()} min" }
                            ?: "No PM2.5 breach predicted 👍",
                        fontSize = 14.sp
                    )
                    if (f.safe_windows.isNotEmpty()) {
                        Text("Safe windows (min): " +
                            f.safe_windows.take(3).joinToString(", ") {
                                "${it.start_min.toInt()}–${it.end_min.toInt()}"
                            }, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun Metric(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier) {
        Column(Modifier.padding(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(value, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Text(label, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
