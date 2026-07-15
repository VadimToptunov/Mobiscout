package com.mobiscout.sdk.core

import android.app.Application
import android.content.pm.PackageManager
import android.os.Build
import java.util.UUID

/**
 * Observation session information
 * 
 * Tracks metadata about the current observation session including:
 * - Session ID (unique identifier)
 * - Device information
 * - App version
 * - OS version
 * - Start time
 */
data class MobiscoutSession(
    val sessionId: String,
    val startTime: Long,
    val deviceModel: String,
    val deviceManufacturer: String,
    val osVersion: String,
    val appVersion: String,
    val appPackage: String
) {
    companion object {
        /**
         * Create new session from application context
         */
        fun create(app: Application): MobiscoutSession {
            return MobiscoutSession(
                sessionId = UUID.randomUUID().toString(),
                startTime = System.currentTimeMillis(),
                deviceModel = Build.MODEL,
                deviceManufacturer = Build.MANUFACTURER,
                osVersion = "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})",
                appVersion = getAppVersion(app),
                appPackage = app.packageName
            )
        }
        
        /**
         * Get app version from PackageManager
         */
        private fun getAppVersion(app: Application): String {
            return try {
                val packageInfo = app.packageManager.getPackageInfo(app.packageName, 0)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    "${packageInfo.versionName} (${packageInfo.longVersionCode})"
                } else {
                    @Suppress("DEPRECATION")
                    "${packageInfo.versionName} (${packageInfo.versionCode})"
                }
            } catch (e: PackageManager.NameNotFoundException) {
                "unknown"
            }
        }
    }
    
    /**
     * Get session duration in milliseconds
     */
    fun getDuration(): Long {
        return System.currentTimeMillis() - startTime
    }
    
    /**
     * Convert session to map for export
     */
    fun toMap(): Map<String, Any> {
        return mapOf(
            "session_id" to sessionId,
            "start_time" to startTime,
            "device_model" to deviceModel,
            "device_manufacturer" to deviceManufacturer,
            "os_version" to osVersion,
            "app_version" to appVersion,
            "app_package" to appPackage
        )
    }
}
