package com.mobiletest.recorder.services

import com.google.gson.JsonObject
import com.intellij.openapi.components.Service
import com.intellij.openapi.project.Project
import com.mobiletest.recorder.rpc.JsonRpcClient
import com.mobiletest.recorder.rpc.JsonRpcNotification
import java.io.File

/**
 * Application-level service for managing the mobile-test-recorder daemon.
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
            // first use, no user Python) or a PATH `observe` CLI for development.
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
}
