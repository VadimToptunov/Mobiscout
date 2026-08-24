package com.mobiletest.recorder.services

import com.google.gson.JsonObject
import com.intellij.openapi.application.PathManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.Disposable
import com.intellij.openapi.project.Project
import com.intellij.util.concurrency.ThreadingAssertions
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
    //
    // Every wrapper below performs a BLOCKING JSON-RPC round-trip — the daemon reads its
    // stdio serially and a device op can take seconds — so it must never run on the EDT.
    // rpc() asserts that: a stray EDT call fails loudly in dev instead of freezing the IDE
    // and waiting for a review to catch it (the P0.4b / U2 / RC3 class).

    /** One blocking JSON-RPC call, asserted off the EDT. Result object, or null when the
     *  engine isn't up. */
    private fun rpc(method: String, params: Map<String, Any> = emptyMap()): JsonObject? {
        ThreadingAssertions.assertBackgroundThread()
        return client?.call(method, params)?.getResultOrThrow()
    }

    fun healthCheck(): JsonObject? = rpc("health/check")

    fun listDevices(platform: String = "all"): JsonObject? = rpc("device/list", mapOf("platform" to platform))

    /** Start streaming the app-under-test's device logs; each line arrives as a
     *  `logs/message` notification the Logs panel renders. iOS uses `simctl log
     *  stream`, Android `adb logcat` scoped to the app's PID. */
    fun startAppLogs(udid: String, bundleId: String, platform: String): JsonObject? =
        rpc("logs/start", mapOf("udid" to udid, "bundle_id" to bundleId, "platform" to platform))

    fun stopAppLogs(): JsonObject? = rpc("logs/stop")

    fun getUiTree(sessionId: String): JsonObject? = rpc("ui/getTree", mapOf("session_id" to sessionId))

    fun getScreenshot(sessionId: String, format: String = "png"): JsonObject? =
        rpc("ui/getScreenshot", mapOf("session_id" to sessionId, "format" to format))

    /**
     * Detect the automation toolchain (Appium, adb/Android SDK, drivers, Xcode)
     * so the setup wizard can tell the user what to fix before crawling — e.g.
     * the ANDROID_HOME an UiAutomator2 Appium session needs. Runs no device.
     */
    fun detectEnvironment(): JsonObject? = rpc("environment/detect")

    /** Boot an emulator/simulator so a session can start on it. */
    fun startDevice(platform: String, target: String): JsonObject? =
        rpc("device/start", mapOf("platform" to platform, "target" to target))

    /** Shut down a running emulator/simulator. */
    fun stopDevice(platform: String, deviceId: String): JsonObject? =
        rpc("device/stop", mapOf("platform" to platform, "device_id" to deviceId))

    /** Installed Android AVDs that can be booted (`emulator -list-avds`). */
    fun listAvds(): JsonObject? = rpc("device/listAvds")

    /** Install a build (.apk / .app) onto a device before crawling. */
    fun installApp(platform: String, deviceId: String, appPath: String): JsonObject? =
        rpc("app/install", mapOf("platform" to platform, "device_id" to deviceId, "app_path" to appPath))

    /** Remove the app after a run (install → crawl → cleanup). */
    fun uninstallApp(platform: String, deviceId: String, packageName: String): JsonObject? =
        rpc("app/uninstall", mapOf("platform" to platform, "device_id" to deviceId, "package" to packageName))

    /**
     * The active entitlement tier + quotas, so the IDE can show limits and upsell.
     * The open-core engine is unlimited (`pro`); a Mobiscout-PRO install with a
     * FREE licence reports `free` with `max_screens`/`max_tests`/`max_targets`.
     */
    fun licenseStatus(): JsonObject? = rpc("license/status")
}
