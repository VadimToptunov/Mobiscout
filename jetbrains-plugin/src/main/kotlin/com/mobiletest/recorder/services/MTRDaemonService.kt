package com.mobiletest.recorder.services

import com.google.gson.JsonObject
import com.intellij.openapi.components.Service
import com.intellij.openapi.project.Project
import com.mobiletest.recorder.rpc.JsonRpcClient
import com.mobiletest.recorder.rpc.JsonRpcNotification
import java.io.File

/**
 * Application-level service for managing the mobiscout daemon.
 */
@Service
class MTRDaemonService {
    private var process: Process? = null
    private var client: JsonRpcClient? = null
    private val listeners = mutableListOf<(JsonRpcNotification) -> Unit>()
    
    @Volatile
    private var isRunning = false
    
    /**
     * Start the daemon process.
     */
    fun start(): Boolean {
        if (isRunning) {
            return true
        }
        
        try {
            // Resolve the engine: a self-contained standalone binary (downloaded on
            // first use, no user Python) or a PATH `mobiscout` CLI for development.
            val command = EngineProvider.resolveDaemonCommand()

            // Start daemon
            val processBuilder = ProcessBuilder(command)
            processBuilder.redirectError(ProcessBuilder.Redirect.to(File("mtr-daemon.log")))
            
            process = processBuilder.start()
            client = JsonRpcClient(process!!)
            
            // Start listening for notifications
            client?.startListening { notification ->
                listeners.forEach { it(notification) }
            }
            
            // Test connection with health check
            val response = client?.call("health/check")
            if (response?.isError() == false) {
                isRunning = true
                return true
            }
            
            return false
        } catch (e: Exception) {
            println("Failed to start daemon: ${e.message}")
            stop()
            return false
        }
    }
    
    /**
     * Stop the daemon.
     */
    fun stop() {
        isRunning = false
        client?.close()
        client = null
        process = null
    }
    
    /**
     * Check if daemon is running.
     */
    fun isRunning(): Boolean = isRunning
    
    /**
     * Get the RPC client.
     */
    fun getClient(): JsonRpcClient? = client
    
    /**
     * Add notification listener.
     */
    fun addNotificationListener(listener: (JsonRpcNotification) -> Unit) {
        listeners.add(listener)
    }
    
    /**
     * Remove notification listener.
     */
    fun removeNotificationListener(listener: (JsonRpcNotification) -> Unit) {
        listeners.remove(listener)
    }
    
    // API Methods
    
    fun healthCheck(): JsonObject? {
        return client?.call("health/check")?.getResultOrThrow()
    }
    
    fun listDevices(platform: String = "all"): JsonObject? {
        val params = mapOf("platform" to platform)
        return client?.call("device/list", params)?.getResultOrThrow()
    }

    /** Start streaming the app-under-test's device logs; each line arrives as a
     *  `logs/message` notification the Logs panel renders. iOS uses `simctl log
     *  stream`, Android `adb logcat` scoped to the app's PID. */
    fun startAppLogs(udid: String, bundleId: String, platform: String): JsonObject? {
        val params = mapOf("udid" to udid, "bundle_id" to bundleId, "platform" to platform)
        return client?.call("logs/start", params)?.getResultOrThrow()
    }

    fun stopAppLogs(): JsonObject? = client?.call("logs/stop", emptyMap<String, Any>())?.getResultOrThrow()
    
    fun getUiTree(sessionId: String): JsonObject? {
        val params = mapOf("session_id" to sessionId)
        return client?.call("ui/getTree", params)?.getResultOrThrow()
    }
    
    fun getScreenshot(sessionId: String, format: String = "png"): JsonObject? {
        val params = mapOf(
            "session_id" to sessionId,
            "format" to format
        )
        return client?.call("ui/getScreenshot", params)?.getResultOrThrow()
    }

    /**
     * Detect the automation toolchain (Appium, adb/Android SDK, drivers, Xcode)
     * so the setup wizard can tell the user what to fix before crawling — e.g.
     * the ANDROID_HOME an UiAutomator2 Appium session needs. Runs no device.
     */
    fun detectEnvironment(): JsonObject? {
        return client?.call("environment/detect")?.getResultOrThrow()
    }

    /** Boot an emulator/simulator so a session can start on it. */
    fun startDevice(platform: String, target: String): JsonObject? {
        val params = mapOf("platform" to platform, "target" to target)
        return client?.call("device/start", params)?.getResultOrThrow()
    }

    /** Shut down a running emulator/simulator. */
    fun stopDevice(platform: String, deviceId: String): JsonObject? {
        val params = mapOf("platform" to platform, "device_id" to deviceId)
        return client?.call("device/stop", params)?.getResultOrThrow()
    }

    /** Installed Android AVDs that can be booted (`emulator -list-avds`). */
    fun listAvds(): JsonObject? = client?.call("device/listAvds", emptyMap<String, Any>())?.getResultOrThrow()

    /** Install a build (.apk / .app) onto a device before crawling. */
    fun installApp(platform: String, deviceId: String, appPath: String): JsonObject? {
        val params = mapOf("platform" to platform, "device_id" to deviceId, "app_path" to appPath)
        return client?.call("app/install", params)?.getResultOrThrow()
    }

    /** Remove the app after a run (install → crawl → cleanup). */
    fun uninstallApp(platform: String, deviceId: String, packageName: String): JsonObject? {
        val params = mapOf("platform" to platform, "device_id" to deviceId, "package" to packageName)
        return client?.call("app/uninstall", params)?.getResultOrThrow()
    }

    /**
     * The active entitlement tier + quotas, so the IDE can show limits and upsell.
     * The open-core engine is unlimited (`pro`); a Mobiscout-PRO install with a
     * FREE licence reports `free` with `max_screens`/`max_tests`/`max_targets`.
     */
    fun licenseStatus(): JsonObject? {
        return client?.call("license/status")?.getResultOrThrow()
    }
}
