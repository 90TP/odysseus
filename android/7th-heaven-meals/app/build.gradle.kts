plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.seventhhaven.meals"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.seventhhaven.meals"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0-webview"
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
