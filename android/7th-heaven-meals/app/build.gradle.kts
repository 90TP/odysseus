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
}
