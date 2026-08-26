package com.mobiletest.recorder.services

import com.google.gson.JsonObject
import com.intellij.openapi.application.PathManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.Disposable
import com.intellij.openapi.project.Project
import com.intellij.openapi.application.ApplicationManager
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

        /** A healthy engine answers health/check in well under this; a wedged one must fail
         *  the start fast rather than pinning the "Starting…" spinner on the RPC backstop. */
        private const val HEALTH_CHECK_TIMEOUT_MS = 15_000L
    }

    /** Human-readable cause of the last failed [start], for the notification surfaces —
     *  so a missing CLI or a health-check error isn't reported as "check your internet". */
    @Volatile
    var lastStartError: String? = null
        private set

    /**
     * Start the daemon process. Synchronized so concurrent callers (tool-window
     * auto-start + a Generate action) don't each spawn a daemon.
     */
    @Synchronized
    fun start(): Boolean {
        if (isRunning && client != null) {
            return true
        }
        lastStartError = null
        var proc: Process? = null
        var rpc: JsonRpcClient? = null
        try {
            // Resolve the engine: a self-contained standalone binary (downloaded on
            // first use, no user Python) or a PATH `mobiscout` CLI for development.
            val command = EngineProvider.resolveDaemonCommand()

            // Start daemon. The engine's stderr goes to the IDE log dir (not the IDE's
            // working directory, which may be read-only or unfindable to the user).
            val processBuilder = ProcessBuilder(command)
            val logFile = File(PathManager.getLogPath(), "mobiscout-daemon.log")
            processBuilder.redirectError(ProcessBuilder.Redirect.to(logFile))
            // Pin the engine's stdio (and filesystem) encoding to UTF-8, which is what
            // JsonRpcClient writes. A Windows Python decodes a PIPED stdin with the ANSI
            // codepage by default, so a request carrying non-ASCII — the project path in
            // every kit/generate, a login waypoint — arrives as mojibake or raises an
            // uncaught UnicodeDecodeError in the daemon's read loop and kills it mid-request.
            processBuilder.environment()["PYTHONUTF8"] = "1"
            processBuilder.environment()["PYTHONIOENCODING"] = "utf-8"

            proc = processBuilder.start()
            rpc = JsonRpcClient(proc)
            rpc.startListening { notification -> notifyListeners(notification) }

            // Test the connection. Short timeout: a healthy engine answers in well under
            // 15 s, and a wedged one must not pin the "Starting…" spinner for 10 minutes.
            val response = rpc.call("health/check", timeoutMs = HEALTH_CHECK_TIMEOUT_MS)
            if (!response.isError()) {
                process = proc
                client = rpc
                isRunning = true
                // Detect the engine dying out from under us (crash, OOM, external kill):
                // stop() fires the state listeners, so the status dot and action enablement
                // heal instead of lying "Running" over a dead process forever.
                proc.onExit().thenRun { onEngineExit(proc) }
                // An engine that died right after answering health/check completes that future
                // before we register, so thenRun runs INLINE on this thread and reenters
                // stop() (same monitor), clearing the state we just set. Firing notifyState(true)
                // afterwards would paint "Running" over a dead engine with nothing left to heal
                // it, and hand the caller a `true` with a null client.
                if (!isRunning) {
                    lastStartError = "The engine exited immediately after starting."
                    return false
                }
                notifyState(true)
                return true
            }
            lastStartError = "Engine health check failed: ${response.error?.message ?: "unknown error"}"
            rpc.close()
            return false
        } catch (e: Exception) {
            LOG.warn("Failed to start mobiscout daemon", e)
            lastStartError = e.message ?: e.toString()
            // Clean up the half-started locals — stop() only touches the (still-null) fields,
            // so without this a daemon that launched but never answered would keep running.
            try {
                rpc?.close()
            } catch (_: Exception) {
            }
            try {
                proc?.destroyForcibly()
            } catch (_: Exception) {
            }
            return false
        }
    }

    /** The engine process ended. Stop (and notify the UI) only if it is still the CURRENT
     *  engine — a stale onExit from an engine we already replaced must not kill its successor. */
    @Synchronized
    private fun onEngineExit(dead: Process) {
        if (process === dead) {
            LOG.warn("Mobiscout engine process exited unexpectedly")
            stop()
        }
    }

    /**
     * Stop the daemon.
     */
    /** Stop the engine off the calling thread. [stop] blocks up to ~5 s waiting for the
     *  process to die, so a UI action (a toolbar/menu click, always on the EDT) must use this
     *  to avoid freezing the IDE. The state listeners still fire (from the pooled thread). */
    fun stopAsync() {
        ApplicationManager.getApplication().executeOnPooledThread { stop() }
    }

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

    /** Fan a daemon notification out to the listeners, each isolated. This runs on the RPC
     *  reader thread, which is shared by every panel and project, so one listener that throws
     *  must not take the whole connection down (the engine's TCP loop isolates its clients
     *  the same way). */
    private fun notifyListeners(notification: JsonRpcNotification) {
        for (listener in listeners) {
            try {
                listener(notification)
            } catch (e: Exception) {
                LOG.warn("A Mobiscout notification listener failed", e)
            }
        }
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
