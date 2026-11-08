package com.vayumitra.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vayumitra.model.Profile

private val ALL_TRIGGERS = listOf("smoke", "dust", "humidity", "voc", "cold-air", "pollen")
private val SEVERITIES = listOf("mild", "moderate", "severe")

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ProfileScreen(
    profile: Profile,
    modifier: Modifier = Modifier,
    onSave: (Profile) -> Unit,
) {
    var severity by remember { mutableStateOf(profile.severity) }
    var triggers by remember { mutableStateOf(profile.triggers.toSet()) }
    var aqiTolerance by remember { mutableStateOf(profile.aqi_tolerance.toFloat()) }
    var humidityThreshold by remember { mutableStateOf((profile.humidity_threshold ?: 70.0).toFloat()) }
    var medication by remember { mutableStateOf(profile.medication ?: "") }
    var saved by remember { mutableStateOf(false) }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Text("Your asthma profile", fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text("Personalizes your risk score, advisories and alert threshold.",
            fontSize = 13.sp)

        Text("Severity", fontWeight = FontWeight.SemiBold)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SEVERITIES.forEach { s ->
                FilterChip(selected = severity == s, onClick = { severity = s; saved = false },
                    label = { Text(s.replaceFirstChar { it.uppercase() }) })
            }
        }

        Text("Triggers", fontWeight = FontWeight.SemiBold)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ALL_TRIGGERS.forEach { t ->
                FilterChip(
                    selected = t in triggers,
                    onClick = {
                        triggers = if (t in triggers) triggers - t else triggers + t; saved = false
                    },
                    label = { Text(t) }
                )
            }
        }

        Text("AQI tolerance: ${aqiTolerance.toInt()}", fontWeight = FontWeight.SemiBold)
        Text("Lower = more sensitive (raises your risk sooner).", fontSize = 12.sp)
        Slider(value = aqiTolerance, onValueChange = { aqiTolerance = it; saved = false },
            valueRange = 0f..300f)

        Text("Humidity alert threshold: ${humidityThreshold.toInt()}%", fontWeight = FontWeight.SemiBold)
        Slider(value = humidityThreshold, onValueChange = { humidityThreshold = it; saved = false },
            valueRange = 20f..95f)

        OutlinedTextField(
            value = medication,
            onValueChange = { medication = it; saved = false },
            label = { Text("Reliever medication (optional)") },
            modifier = Modifier.fillMaxWidth()
        )

        Button(
            onClick = {
                onSave(
                    profile.copy(
                        severity = severity,
                        triggers = triggers.toList(),
                        aqi_tolerance = aqiTolerance.toDouble(),
                        humidity_threshold = humidityThreshold.toDouble(),
                        medication = medication.ifBlank { null },
                    )
                )
                saved = true
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (saved) "Saved ✓" else "Save profile")
        }
    }
}
