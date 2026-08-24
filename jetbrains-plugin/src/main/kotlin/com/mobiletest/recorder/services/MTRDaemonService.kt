package com.mobiletest.recorder.services

import com.google.gson.JsonObject
import com.intellij.openapi.application.PathManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.Disposable
import com.intellij.openapi.project.Project
import com.mobiletest.recorder.rpc.JsonRpcClient
import com.mobiletest.recorder.rpc.JsonRpcNotification
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Application-level service for managing the mobiscout daemon.
 *
 * As an application service it is a [Disposable] tied to the IDE lifecycle, so the engine
 * process is stopped on shutdown instead of being orphaned. [start] is synchronized so a
 * tool-window auto-start and a Generate click can't race into two daemons.
 */
@Service
class MTRDaemonService : Disposable {
    private var process: Process? = null
    @Volatile
    private var client: JsonRpcClient? = null
    // Notified from the RPC reader thread while listeners are added/removed on the EDT —
    // a copy-on-write list makes that iteration/mutation safe.
    private val listeners = CopyOnWriteArrayList<(JsonRpcNotification) -> Unit>()
    // Daemon-lifecycle listeners: fired on every start/stop so any UI (the tool-window
    // status dot) reflects the real state no matter which path started/stopped it — the
    // toolbar action, the Tools-menu action, or an internal failure. true = running.
    private val stateListeners = CopyOnWriteArrayList<(Boolean) -> Unit>()

    @Volatile
    private var isRunning = false

    private companion object {
        private val LOG = logger<MTRDaemonService>()
    }

    /**
     * Start the daemon process. Synchronized so concurrent callers (tool-window
     * auto-start + a Generate action) don't each spawn a daemon.
     */
    @Synchronized
    fun start(): Boolean {
        if (isRunning && client != null) {
            return true
        }

        try {
            // Resolve the engine: a self-contained standalone binary (downloaded on
            // first use, no user Python) or a PATH `mobiscout` CLI for development.
            val command = EngineProvider.resolveDaemonCommand()

            // Start daemon. The engine's stderr goes to the IDE log dir (not the IDE's
            // working directory, which may be read-only or unfindable to the user).
            val processBuilder = ProcessBuilder(command)
            val logFile = File(PathManager.getLogPath(), "mobiscout-daemon.log")
            processBuilder.redirectError(ProcessBuilder.Redirect.to(logFile))

            val proc = processBuilder.start()
            val rpc = JsonRpcClient(proc)
            rpc.startListening { notification -> listeners.forEach { it(notification) } }

            // Test connection with health check
            val response = rpc.call("health/check")
            if (response.isError() == false) {
                process = proc
                client = rpc
                isRunning = true
                notifyState(true)
                return true
            }
            rpc.close()
            return false
        } catch (e: Exception) {
            LOG.warn("Failed to start mobiscout daemon", e)
            stop()
            return false
        }
    }

    /**
     * Stop the daemon.
     */
    @Synchronized
    fun stop() {
        val wasRunning = isRunning
        isRunning = false
        client?.close()
        client = null
        process = null
        if (wasRunning) notifyState(false)
    }

    /** Add/remove a daemon-lifecycle listener (true = started, false = stopped). Fired
     *  from whatever thread called start()/stop(), so a Swing listener must marshal to the
     *  EDT itself. */
    fun addStateListener(listener: (Boolean) -> Unit) {
        stateListeners.add(listener)
    }

    fun removeStateListener(listener: (Boolean) -> Unit) {
        stateListeners.remove(listener)
    }

    private fun notifyState(running: Boolean) {
        stateListeners.forEach { it(running) }
    }

    /** Stop the engine when the IDE (and thus this application service) is disposed. */
    override fun dispose() {
        stop()
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
