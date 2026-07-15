plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.findemo"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.findemo"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    // ============================================================
    // BUILD VARIANTS - Key architectural feature!
    // ============================================================
    flavorDimensions += "environment"
    
    productFlavors {
        create("mobiscout") {
            dimension = "environment"
            applicationIdSuffix = ".mobiscout"
            versionNameSuffix = "-mobiscout"
            
            // Enable Mobiscout SDK
            buildConfigField("Boolean", "MOBISCOUT_ENABLED", "true")
            buildConfigField("Boolean", "TEST_MODE", "false")
            
            // Security settings - RELAXED for testing
            buildConfigField("Boolean", "CRYPTO_EXPORT_ENABLED", "true")
            buildConfigField("Boolean", "CERT_PINNING_ENABLED", "false")
            buildConfigField("Boolean", "ROOT_DETECTION_ENABLED", "false")
            
            // Custom app name for mobiscout variant
            resValue("string", "app_name", "FinDemo ")
            
            manifestPlaceholders["appIcon"] = "@mipmap/ic_launcher_observe"
        }
        
        create("test") {
            dimension = "environment"
            applicationIdSuffix = ".test"
            versionNameSuffix = "-test"
            
            // Clean build without SDK, test-friendly settings
            buildConfigField("Boolean", "MOBISCOUT_ENABLED", "false")
            buildConfigField("Boolean", "TEST_MODE", "true")
            
            // Security settings - RELAXED for automated testing
            buildConfigField("Boolean", "CRYPTO_EXPORT_ENABLED", "false")
            buildConfigField("Boolean", "CERT_PINNING_ENABLED", "false")
            buildConfigField("Boolean", "ROOT_DETECTION_ENABLED", "false")
            
            resValue("string", "app_name", "FinDemo 🧪")
            
            // Disable minification for tests
            isMinifyEnabled = false
            
            manifestPlaceholders["appIcon"] = "@mipmap/ic_launcher_test"
        }
        
        create("production") {
            dimension = "environment"
            
            // Production build - MAXIMUM SECURITY
            buildConfigField("Boolean", "MOBISCOUT_ENABLED", "false")
            buildConfigField("Boolean", "TEST_MODE", "false")
            
            // Security settings - STRICT for production
            buildConfigField("Boolean", "CRYPTO_EXPORT_ENABLED", "false")
            buildConfigField("Boolean", "CERT_PINNING_ENABLED", "true")
            buildConfigField("Boolean", "ROOT_DETECTION_ENABLED", "true")
            
            resValue("string", "app_name", "FinDemo")
            
            manifestPlaceholders["appIcon"] = "@mipmap/ic_launcher"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isMinifyEnabled = false
            isDebuggable = true
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
        kotlinCompilerExtensionVersion = "1.5.4"
    }
    
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    // Mobiscout SDK - ONLY for mobiscout build
    "observeImplementation"(project(":mobiscout-sdk"))
    
    // AndroidX Core
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.6.2")
    implementation("androidx.activity:activity-compose:1.8.1")
    
    // Compose
    implementation(platform("androidx.compose:compose-bom:2023.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    
    // Navigation
    implementation("androidx.navigation:navigation-compose:2.7.5")
    
    // ViewModel
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.6.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.6.2")
    
    // ViewPager2 (for onboarding)
    implementation("androidx.viewpager2:viewpager2:1.0.0")
    implementation("com.google.accompanist:accompanist-pager:0.32.0")
    implementation("com.google.accompanist:accompanist-pager-indicators:0.32.0")
    
    // WebView
    implementation("androidx.webkit:webkit:1.9.0")
    
    // Network
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    
    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    
    // Room (local database)
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    
    // Datastore
    implementation("androidx.datastore:datastore-preferences:1.0.0")
    
    // Gson
    implementation("com.google.code.gson:gson:2.10.1")
    
    // ============================================================
    // SECURITY DEPENDENCIES
    // ============================================================
    
    // Encrypted SharedPreferences (for secure token storage)
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    
    // Biometric Authentication
    implementation("androidx.biometric:biometric:1.2.0-alpha05")
    
    // Security providers
    implementation("com.google.crypto.tink:tink-android:1.11.0")
    
    // ============================================================
    
    // Regula Document Reader SDK for KYC
    implementation("com.regula.documentreader:api:7.6.+@aar") {
        isTransitive = true
    }
    
    // Camera
    implementation("androidx.camera:camera-camera2:1.3.1")
    implementation("androidx.camera:camera-lifecycle:1.3.1")
    implementation("androidx.camera:camera-view:1.3.1")
    
    // Testing
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
    androidTestImplementation(platform("androidx.compose:compose-bom:2023.10.01"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    
    // Debug
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}

