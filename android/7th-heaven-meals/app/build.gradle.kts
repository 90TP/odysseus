import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Aerith error reporting. Set these in local.properties (never committed):
//   aerith.url=https://your-odysseus-host:7000
//   aerith.token=ody_...   (a paired-device token from Odysseus)
// Leave them out and reporting is off.
val localProps = Properties().apply {
    val f = rootProject.file("local.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
fun buildConfigString(value: String?): String =
    "\"" + (value ?: "").replace("\\", "\\\\").replace("\"", "\\\"") + "\""

android {
    namespace = "com.seventhhaven.meals"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.seventhhaven.meals"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0-webview"

        buildConfigField("String", "AERITH_URL", buildConfigString(localProps.getProperty("aerith.url")))
        buildConfigField("String", "AERITH_TOKEN", buildConfigString(localProps.getProperty("aerith.token")))
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.activity:activity-ktx:1.10.0")

    // Temporarily retained because the previous native API helper source files still
    // exist in this branch. The WebView app does not use them at runtime.
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-moshi:2.11.0")
    implementation("com.squareup.moshi:moshi-kotlin:1.15.1")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
}
