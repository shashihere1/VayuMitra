package com.vayumitra.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vayumitra.model.EmergencyAlert

/**
 * Full-screen red emergency. Shows the reason + personalized recommended action,
 * a one-tap "Navigate to <safe zone>" (Google Maps intent) and "I'm safe"
 * (publishes EmergencyAck to clear the cascade / silence the buzzer).
 */
@Composable
fun EmergencyScreen(
    alert: EmergencyAlert,
    onSafe: () -> Unit,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFFB91C1C))
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("⚠️ AIR EMERGENCY", fontSize = 34.sp, fontWeight = FontWeight.Black, color = Color.White,
            textAlign = TextAlign.Center)
        Text("Risk ${"%.0f".format(alert.risk_score)} / 100", fontSize = 22.sp, color = Color.White)
        Text(alert.reason, fontSize = 18.sp, color = Color.White, textAlign = TextAlign.Center)
        alert.recommended_action?.let {
            Text(it, fontSize = 16.sp, color = Color.White.copy(alpha = 0.9f), textAlign = TextAlign.Center)
        }

        alert.safe_zone?.let { zone ->
            Button(
                onClick = {
                    // geo intent -> Google Maps navigation to the safe zone
                    val uri = Uri.parse(
                        "geo:${zone.lat},${zone.lon}?q=${zone.lat},${zone.lon}(${Uri.encode(zone.name)})"
                    )
                    val intent = Intent(Intent.ACTION_VIEW, uri).apply {
                        setPackage("com.google.android.apps.maps")
                    }
                    val fallback = Intent(Intent.ACTION_VIEW, uri)
                    context.startActivity(if (intent.resolveActivity(context.packageManager) != null) intent else fallback)
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color(0xFFB91C1C))
            ) {
                Text("🧭 Navigate to ${zone.name}  (${zone.distance_m.toInt()} m)",
                    fontWeight = FontWeight.Bold)
            }
        }

        Button(
            onClick = onSafe,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF16A34A))
        ) {
            Text("✅ I'm safe", fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Color.White)
        }
        OutlinedButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
            Text("Dismiss", color = Color.White)
        }
    }
}
