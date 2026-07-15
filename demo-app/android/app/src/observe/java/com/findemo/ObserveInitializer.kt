package com.findemo

import android.app.Application
import android.util.Log
import com.mobiscout.sdk.MobiscoutSDK
import com.mobiscout.sdk.core.MobiscoutConfig

/**
 * Initializer for Mobiscout build variant
 * 
 * This file ONLY exists in mobiscout source set
 * It will NOT be compiled into test or prod builds
 */
object MobiscoutInitializer {
    
    private const val TAG = "MobiscoutInit"
    
    fun initialize(app: Application) {
        Log.i(TAG, " Initializing Mobiscout SDK for mobiscout build")
        
        try {
            MobiscoutSDK.initialize(
                app = app,
                config = MobiscoutConfig(
                    appVersion = BuildConfig.VERSION_NAME,
                    serverUrl = "http://10.0.2.2:8080",  // Android emulator localhost
                    batchSize = 50,
                    flushIntervalMs = 5000
                )
            )
            
            Log.i(TAG, " Mobiscout SDK initialized successfully")
        } catch (e: Exception) {
            Log.e(TAG, " Failed to initialize Mobiscout SDK", e)
        }
    }
}

/**
 * Extension function for Application class
 * Available ONLY in mobiscout build
 */
fun Application.initializeMobiscoutSDK() {
    MobiscoutInitializer.initialize(this)
}

