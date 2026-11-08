package com.vayumitra.data

import android.content.Context
import android.util.Log
import com.vayumitra.model.Profile
import com.vayumitra.model.SensorReading
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.nnapi.NnApiDelegate
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel
import kotlin.math.max
import kotlin.math.min

/**
 * On-device risk so the phone shows a value even with Wi-Fi off.
 *
 * Primary: LiteRT/TFLite `risk.tflite` from assets, trying NNAPI (NPU) → CPU.
 * Fallback: a Kotlin port of the documented heuristic (always available), which
 * also supplies `topFactors`. Either way the phone is functional offline.
 */
class RiskModel(context: Context) {

    var engine: String = "heuristic"
        private set

    private var interpreter: Interpreter? = null
    private var nnApiDelegate: NnApiDelegate? = null
    private var scalerMean: FloatArray? = null
    private var scalerStd: FloatArray? = null

    init {
        tryLoadTflite(context)
    }

    private fun tryLoadTflite(context: Context) {
        try {
            val model = loadAsset(context, "risk.tflite") ?: return
            // NNAPI first (routes to NPU/DSP where available), then plain CPU.
            interpreter = try {
                nnApiDelegate = NnApiDelegate()
                Interpreter(model, Interpreter.Options().addDelegate(nnApiDelegate)).also {
                    engine = "npu/nnapi"
                }
            } catch (e: Exception) {
                Log.w(TAG, "NNAPI delegate failed (${e.message}); CPU")
                Interpreter(model).also { engine = "cpu" }
            }
            loadScaler(context)
            Log.i(TAG, "on-device model loaded (engine=$engine)")
        } catch (e: Exception) {
            Log.i(TAG, "no on-device tflite (${e.message}); using heuristic")
            interpreter = null
            engine = "heuristic"
        }
    }

    private fun loadAsset(context: Context, name: String): ByteBuffer? {
        return try {
            val afd = context.assets.openFd(name)
            FileInputStream(afd.fileDescriptor).channel.use { ch ->
                ch.map(FileChannel.MapMode.READ_ONLY, afd.startOffset, afd.declaredLength)
            }
        } catch (e: Exception) {
            null
        }
    }

    private fun loadScaler(context: Context) {
        try {
            val txt = context.assets.open("scaler.json").bufferedReader().use { it.readText() }
            val mean = Regex("\"mean\"\\s*:\\s*\\[([^]]*)]").find(txt)?.groupValues?.get(1)
            val std = Regex("\"std\"\\s*:\\s*\\[([^]]*)]").find(txt)?.groupValues?.get(1)
            scalerMean = mean?.split(",")?.map { it.trim().toFloat() }?.toFloatArray()
            scalerStd = std?.split(",")?.map { it.trim().toFloat() }?.toFloatArray()
        } catch (e: Exception) {
            scalerMean = null; scalerStd = null
        }
    }

    /** Returns risk score [0,100] plus up to 3 top factors. */
    fun compute(reading: SensorReading, profile: Profile?): Pair<Double, List<String>> {
        val feats = buildFeatures(reading, profile)
        val (hScore, factors) = heuristic(feats)
        val itp = interpreter ?: return hScore to factors
        return try {
            val input = feats.copyOf()
            val mean = scalerMean; val std = scalerStd
            if (mean != null && std != null && mean.size == input.size) {
                for (i in input.indices) input[i] = (input[i] - mean[i]) / if (std[i] == 0f) 1f else std[i]
            }
            val inBuf = ByteBuffer.allocateDirect(4 * input.size).order(ByteOrder.nativeOrder())
            input.forEach { inBuf.putFloat(it) }
            inBuf.rewind()
            val out = ByteBuffer.allocateDirect(4).order(ByteOrder.nativeOrder())
            itp.run(inBuf, out)
            out.rewind()
            val score = out.float.toDouble().coerceIn(0.0, 100.0)
            score to factors
        } catch (e: Exception) {
            Log.w(TAG, "tflite run failed (${e.message}); heuristic")
            hScore to factors
        }
    }

    fun close() {
        interpreter?.close()
        nnApiDelegate?.close()
    }

    // ---- feature vector (mirror FEATURE_ORDER; phone has no rate history) ----
    private fun buildFeatures(r: SensorReading, p: Profile?): FloatArray {
        val pm25 = r.pm25.toFloat()
        val pm10 = (r.pm10 ?: r.pm25 * 1.4).toFloat()
        val severity = when (p?.severity) { "mild" -> 0f; "severe" -> 2f; else -> 1f }
        val sensitivity = (1.0 - (p?.aqi_tolerance ?: 100.0) / 150.0).coerceIn(0.0, 1.0).toFloat()
        return floatArrayOf(
            pm25, pm10, r.temperature.toFloat(), r.humidity.toFloat(),
            (r.voc_index ?: 0.0).toFloat(), (r.pressure ?: 0.0).toFloat(),
            0f, 0f, 0f, severity, sensitivity
        )
    }

    // ---- Kotlin port of ai_pc/ml/heuristic.py ----
    private fun heuristic(f: FloatArray): Pair<Double, List<String>> {
        fun clamp(x: Double, lo: Double, hi: Double) = max(lo, min(hi, x))
        val pm25 = f[0].toDouble(); val humidity = f[3].toDouble()
        val voc = f[4].toDouble(); val pressure = f[5].toDouble()
        val tempRate = f[8].toDouble(); val pm25Rate = f[6].toDouble(); val humRate = f[7].toDouble()
        val severity = f[9].toInt().coerceIn(0, 2); val sensitivity = clamp(f[10].toDouble(), 0.0, 1.0)

        val c = HashMap<String, Double>()
        c["high PM2.5"] = 60.0 * clamp(pm25 / 200.0, 0.0, 1.0)
        c["humidity out of comfort range"] = when {
            humidity > 60 -> 12.0 * clamp((humidity - 60) / 35.0, 0.0, 1.0)
            humidity < 30 -> 8.0 * clamp((30 - humidity) / 30.0, 0.0, 1.0)
            else -> 0.0
        }
        c["elevated VOC / gas"] = 15.0 * clamp(voc / 500.0, 0.0, 1.0)
        c["rapid temperature drop"] = 8.0 * clamp(-tempRate / 2.0, 0.0, 1.0)
        c["low / falling pressure"] = if (pressure > 0) 5.0 * clamp((1010 - pressure) / 30.0, 0.0, 1.0) else 0.0
        c["rapid PM2.5 rise"] = 10.0 * clamp(pm25Rate / 20.0, 0.0, 1.0)
        c["rapid humidity rise"] = 5.0 * clamp(humRate / 10.0, 0.0, 1.0)

        val sevMult = doubleArrayOf(0.85, 1.0, 1.2)[severity]
        val scale = sevMult * (1.0 + 0.5 * sensitivity)
        val score = clamp(c.values.sum() * scale, 0.0, 100.0)
        val factors = c.entries.filter { it.value > 0.5 }.sortedByDescending { it.value }
            .take(3).map { it.key }.ifEmpty { listOf("nominal conditions") }
        return score to factors
    }

    companion object {
        private const val TAG = "VayuRiskModel"
        fun levelFor(score: Double) = when {
            score < 25 -> "low"; score < 50 -> "moderate"; score < 75 -> "high"; else -> "critical"
        }
    }
}
