package com.findemo

import android.app.Application
import android.util.Log

class FinDemoApplication : Application() {
    
    override fun onCreate() {
        super.onCreate()
        
        Log.d(TAG, "App starting - Build config:")
        Log.d(TAG, "  MOBISCOUT_ENABLED: ${BuildConfig.MOBISCOUT_ENABLED}")
        Log.d(TAG, "  TEST_MODE: ${BuildConfig.TEST_MODE}")
        
        // Initialize based on build variant
        when {
            BuildConfig.MOBISCOUT_ENABLED -> {
                initializeMobiscoutMode()
            }
            BuildConfig.TEST_MODE -> {
                initializeTestMode()
            }
            else -> {
                initializeProductionMode()
            }
        }
    }
    
    private fun initializeMobiscoutMode() {
        Log.i(TAG, " Mobiscout mode enabled - Initializing SDK")
        // Call mobiscout source set extension function to initialize SDK
        // This extension function is ONLY available in mobiscout build variant
        this.initializeMobiscoutSDK()
    }
    
    private fun initializeTestMode() {
        Log.i(TAG, "🧪 Test mode enabled")
        // Test-specific initialization
        // Could disable analytics, speed up animations, etc.
    }
    
    private fun initializeProductionMode() {
        Log.i(TAG, " Production mode")
        // Normal app initialization
        // Analytics, crashlytics, etc.
    }
    
    companion object {
        private const val TAG = "FinDemoApp"
    }
}

