package com.findemo.security

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import java.io.File

/**
 * Root Detection for Android
 * 
 * Detects if device is rooted to prevent security bypass.
 * 
 * IMPORTANT:
 * - ENABLED in production builds
 * - Can be disabled in mobiscout/test builds for testing
 * 
 * Detection methods:
 * - Check for su binary
 * - Check for root management apps
 * - Check for dangerous properties
 * - Check for test-keys build
 */
object RootDetection {
    
    private const val TAG = "RootDetection"
    
    /**
     * Check if device is rooted
     * 
     * @param strictMode If true, uses all detection methods (production)
     *                   If false, uses basic checks only (test)
     * @return true if root is detected
     */
    fun isDeviceRooted(context: Context, strictMode: Boolean = true): Boolean {
        val checks = mutableListOf<Pair<String, Boolean>>()
        
        // Check 1: su binary
        checks.add("su_binary" to checkForSuBinary())
        
        // Check 2: Root management apps
        checks.add("root_apps" to checkForRootApps(context))
        
        // Check 3: Dangerous properties
        checks.add("properties" to checkForDangerousProps())
        
        if (strictMode) {
            // Check 4: RW paths
            checks.add("rw_paths" to checkForRWPaths())
            
            // Check 5: Test-keys
            checks.add("test_keys" to checkForTestKeys())
            
            // Check 6: Dangerous files
            checks.add("dangerous_files" to checkForDangerousFiles())
        }
        
        val rootDetected = checks.any { it.second }
        
        if (rootDetected) {
            val failedChecks = checks.filter { it.second }.map { it.first }
            Log.w(TAG, " ROOT DETECTED! Failed checks: $failedChecks")
            
            SecurityMonitor.reportSecurityEvent(
                SecurityEvent.ROOT_DETECTED,
                "checks" to failedChecks.joinToString(","),
                "strict_mode" to strictMode.toString()
            )
        } else {
            Log.i(TAG, " No root detected")
        }
        
        return rootDetected
    }
    
    /**
     * Check for su binary in common locations
     */
    private fun checkForSuBinary(): Boolean {
        val paths = listOf(
            "/system/app/Superuser.apk",
            "/sbin/su",
            "/system/bin/su",
            "/system/xbin/su",
            "/data/local/xbin/su",
            "/data/local/bin/su",
            "/system/sd/xbin/su",
            "/system/bin/failsafe/su",
            "/data/local/su",
            "/su/bin/su"
        )
        
        return paths.any { path ->
            try {
                File(path).exists()
            } catch (e: Exception) {
                false
            }
        }
    }
    
    /**
     * Check for root management apps
     */
    private fun checkForRootApps(context: Context): Boolean {
        val rootApps = listOf(
            "com.noshufou.android.su",
            "com.noshufou.android.su.elite",
            "eu.chainfire.supersu",
            "com.koushikdutta.superuser",
            "com.thirdparty.superuser",
            "com.yellowes.su",
            "com.topjohnwu.magisk",
            "com.kingroot.kinguser",
            "com.kingo.root",
            "com.smedialink.oneclickroot",
            "com.zhiqupk.root.global",
            "com.alephzain.framaroot"
        )
        
        val packageManager = context.packageManager
        
        return rootApps.any { packageName ->
            try {
                packageManager.getPackageInfo(packageName, 0)
                true
            } catch (e: PackageManager.NameNotFoundException) {
                false
            }
        }
    }
    
    /**
     * Check for dangerous system properties
     */
    private fun checkForDangerousProps(): Boolean {
        val dangerousProps = mapOf(
            "ro.debuggable" to "1",
            "ro.secure" to "0"
        )
        
        return dangerousProps.any { (key, value) ->
            try {
                val prop = System.getProperty(key)
                prop == value
            } catch (e: Exception) {
                false
            }
        }
    }
    
    /**
     * Check if system partitions are mounted as RW
     */
    private fun checkForRWPaths(): Boolean {
        val paths = arrayOf("/system", "/system/bin", "/system/sbin", "/system/xbin", "/vendor/bin", "/sbin", "/etc")
        
        return try {
            val process = Runtime.getRuntime().exec("mount")
            val input = process.inputStream.bufferedReader().readText()
            
            paths.any { path ->
                input.contains("$path") && input.contains("rw,")
            }
        } catch (e: Exception) {
            false
        }
    }
    
    /**
     * Check if device is built with test-keys
     */
    private fun checkForTestKeys(): Boolean {
        val buildTags = Build.TAGS
        return buildTags != null && buildTags.contains("test-keys")
    }
    
    /**
     * Check for dangerous files
     */
    private fun checkForDangerousFiles(): Boolean {
        val dangerousFiles = listOf(
            "/system/app/Superuser.apk",
            "/system/etc/init.d/99SuperSUDaemon",
            "/dev/com.koushikdutta.superuser.daemon/",
            "/system/xbin/daemonsu"
        )
        
        return dangerousFiles.any { path ->
            try {
                File(path).exists()
            } catch (e: Exception) {
                false
            }
        }
    }
    
    /**
     * Execute command to check if su is accessible
     */
    private fun canExecuteSuCommands(): Boolean {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("/system/xbin/which", "su"))
            val input = process.inputStream.bufferedReader().readText()
            input.isNotEmpty()
        } catch (e: Exception) {
            false
        }
    }
    
    /**
     * Get detailed root detection report
     */
    fun getRootDetectionReport(context: Context): Map<String, Boolean> {
        return mapOf(
            "su_binary" to checkForSuBinary(),
            "root_apps" to checkForRootApps(context),
            "dangerous_props" to checkForDangerousProps(),
            "rw_paths" to checkForRWPaths(),
            "test_keys" to checkForTestKeys(),
            "dangerous_files" to checkForDangerousFiles()
        )
    }
}

/**
 * Emulator Detection
 */
object EmulatorDetection {
    
    private const val TAG = "EmulatorDetection"
    
    /**
     * Check if running on emulator
     */
    fun isEmulator(): Boolean {
        val checks = listOf(
            Build.FINGERPRINT.startsWith("generic"),
            Build.FINGERPRINT.startsWith("unknown"),
            Build.MODEL.contains("google_sdk"),
            Build.MODEL.contains("Emulator"),
            Build.MODEL.contains("Android SDK built for x86"),
            Build.MANUFACTURER.contains("Genymotion"),
            Build.BRAND.startsWith("generic") && Build.DEVICE.startsWith("generic"),
            "google_sdk" == Build.PRODUCT
        )
        
        val isEmulator = checks.any { it }
        
        if (isEmulator) {
            Log.i(TAG, "Running on emulator")
        }
        
        return isEmulator
    }
}

/**
 * Tamper Detection
 */
object TamperDetection {
    
    private const val TAG = "TamperDetection"
    
    /**
     * Check if app has been tampered with
     */
    fun isTampered(context: Context): Boolean {
        val checks = mutableListOf<Pair<String, Boolean>>()
        
        // Check 1: Installer package
        checks.add("installer" to checkInstaller(context))
        
        // Check 2: Debuggable flag
        checks.add("debuggable" to checkDebuggable(context))
        
        val tampered = checks.any { it.second }
        
        if (tampered) {
            val failedChecks = checks.filter { it.second }.map { it.first }
            Log.w(TAG, " TAMPER DETECTED! Failed checks: $failedChecks")
            
            SecurityMonitor.reportSecurityEvent(
                SecurityEvent.TAMPER_DETECTED,
                "checks" to failedChecks.joinToString(",")
            )
        }
        
        return tampered
    }
    
    /**
     * Check installer package (should be Play Store in production)
     */
    private fun checkInstaller(context: Context): Boolean {
        val installer = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            context.packageManager.getInstallSourceInfo(context.packageName).installingPackageName
        } else {
            @Suppress("DEPRECATION")
            context.packageManager.getInstallerPackageName(context.packageName)
        }
        
        val validInstallers = listOf(
            "com.android.vending",  // Google Play Store
            "com.google.android.feedback"  // Google Play Store alternative
        )
        
        // In debug/mobiscout builds, allow any installer
        if (BuildConfig.DEBUG) {
            return false
        }
        
        return installer !in validInstallers
    }
    
    /**
     * Check if app is debuggable (shouldn't be in production)
     */
    private fun checkDebuggable(context: Context): Boolean {
        val appFlags = context.applicationInfo.flags
        val isDebuggable = (appFlags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
        
        // Debuggable should only be true in debug builds
        return isDebuggable && !BuildConfig.DEBUG
    }
}

