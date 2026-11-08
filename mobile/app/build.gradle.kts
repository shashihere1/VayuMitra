plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "com.vayumitra"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.vayumitra"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        // Broker + identity. Override at build time:
        //   ./gradlew installDebug -PMQTT_HOST=192.168.1.42
        buildConfigField("String", "MQTT_HOST",
            "\"${project.findProperty("MQTT_HOST") ?: "10.0.2.2"}\"")
        buildConfigField("int", "MQTT_PORT",
            "${project.findProperty("MQTT_PORT") ?: 1883}")
        buildConfigField("String", "USER_ID",
            "\"${project.findProperty("USER_ID") ?: "demo-user"}\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }
    // Don't compress the tflite model in assets.
    androidResources {
        noCompress += "tflite"
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)

    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.3")
    implementation("androidx.activity:activity-compose:1.9.0")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")

    // MQTT: HiveMQ client (Paho is an alternative fallback).
    implementation("com.hivemq:hivemq-mqtt-client:1.3.3")

    // JSON
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")

    // On-device ML: LiteRT / TFLite (optional; app falls back if model absent).
    implementation("org.tensorflow:tensorflow-lite:2.16.1")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
