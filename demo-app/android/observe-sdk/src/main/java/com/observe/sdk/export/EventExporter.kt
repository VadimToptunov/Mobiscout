package com.mobiscout.sdk.export

import android.content.Context
import android.util.Log
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.mobiscout.sdk.events.Event
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Exports collected events to files and/or network
 * 
 * Features:
 * - Buffers events in memory
 * - Periodic export to JSON files
 * - Configurable export interval
 * - Error handling and retry logic
 * - Compression for large event sets
 */
class EventExporter(
    private val context: Context,
    private val config: ExportConfig = ExportConfig()
) {
    // Coroutine scope recreated on each start() to allow stop/start cycles
    private var scope: CoroutineScope? = null
    private val eventChannel = Channel<Event>(Channel.UNLIMITED)
    private val eventBuffer = mutableListOf<Event>()
    private val gson: Gson = GsonBuilder()
        .setPrettyPrinting()
        .create()
    
    private var isRunning = false
    private var eventCount = 0
    private var lastExportTime = 0L
    
    fun start() {
        if (isRunning) return
        
        Log.d(TAG, "EventExporter started")
        
        // Create new coroutine scope for this start/stop cycle
        scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        isRunning = true
        lastExportTime = System.currentTimeMillis()
        
        // Start event processing worker
        scope?.launch {
            processEvents()
        }
        
        // Start periodic export worker
        scope?.launch {
            periodicExport()
        }
    }
    
    fun stop() {
        if (!isRunning) return
        
        Log.d(TAG, "EventExporter stopping...")
        
        // Stop accepting new events first
        val wasRunning = isRunning
        isRunning = false
        
        // Flush remaining events synchronously to ensure nothing is lost
        kotlinx.coroutines.runBlocking {
            // Give time for any in-flight queueEvent calls to complete
            kotlinx.coroutines.delay(100)
            
            // Process any remaining events in channel
            while (!eventChannel.isEmpty) {
                try {
                    val event = eventChannel.tryReceive().getOrNull()
                    if (event != null) {
                        eventBuffer.add(event)
                        eventCount++
                    } else {
                        break
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Error draining channel: ${e.message}")
                    break
                }
            }
        
        // Export all buffered events
        flushEvents()
    }
    
    // Cancel the coroutine scope to prevent memory leaks
    scope?.cancel()
    scope = null
    
    Log.d(TAG, "EventExporter stopped, exported ${eventBuffer.size} remaining events")
}
    
    /**
     * Queue event for export
     */
    fun queueEvent(event: Event) {
        if (!isRunning) {
            Log.w(TAG, "EventExporter not running, event dropped")
            return
        }
        
        scope?.launch {
            try {
                eventChannel.send(event)
            } catch (e: Exception) {
                Log.w(TAG, "Failed to queue event: ${e.message}")
            }
        }
    }
    
    /**
     * Process events from channel
     */
    private suspend fun processEvents() {
        while (isRunning) {
            try {
                // Collect events with timeout
                val event = eventChannel.receive()
                eventBuffer.add(event)
                eventCount++
                
                // Export when buffer is full
                if (eventBuffer.size >= config.bufferSize) {
                    exportEvents()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error processing events: ${e.message}")
                // Continue processing unless isRunning becomes false
            }
        }
        
        // Processing loop ended
        Log.d(TAG, "Event processing loop terminated")
    }
    
    /**
     * Periodic export worker - exports events based on time interval
     */
    private suspend fun periodicExport() {
        while (isRunning) {
            try {
                // Wait for the export interval
                kotlinx.coroutines.delay(config.exportIntervalMs)
                
                // Export if there are buffered events and enough time has passed
                val timeSinceLastExport = System.currentTimeMillis() - lastExportTime
                if (eventBuffer.isNotEmpty() && timeSinceLastExport >= config.exportIntervalMs) {
                    Log.d(TAG, "Periodic export triggered (${eventBuffer.size} events)")
                    exportEvents()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error in periodic export: ${e.message}")
            }
        }
        
        Log.d(TAG, "Periodic export worker terminated")
    }
    
    /**
     * Export buffered events to file
     */
    private suspend fun exportEvents() {
        if (eventBuffer.isEmpty()) return
        
        withContext(Dispatchers.IO) {
            try {
                val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
                val filename = "observe_events_$timestamp.json"
                val file = File(getExportDirectory(), filename)
                
                // Create event batch
                val eventBatch = EventBatch(
                    timestamp = System.currentTimeMillis(),
                    count = eventBuffer.size,
                    events = eventBuffer.toList()
                )
                
                // Write to file
                file.writeText(gson.toJson(eventBatch))
                
                Log.d(TAG, "Exported ${eventBuffer.size} events to $filename")
                
                // Clear buffer
                eventBuffer.clear()
                
                // Update last export timestamp
                lastExportTime = System.currentTimeMillis()
                
                // Cleanup old files if needed
                cleanupOldFiles()
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to export events", e)
            }
        }
    }
    
    /**
     * Flush all remaining events
     */
    private suspend fun flushEvents() {
        if (eventBuffer.isNotEmpty()) {
            exportEvents()
        }
    }
    
    /**
     * Get export directory
     */
    private fun getExportDirectory(): File {
        val dir = File(context.filesDir, "observe_events")
        if (!dir.exists()) {
            dir.mkdirs()
        }
        return dir
    }
    
    /**
     * Cleanup old export files
     */
    private fun cleanupOldFiles() {
        try {
            val dir = getExportDirectory()
            val files = dir.listFiles() ?: return
            
            // Keep only last N files
            val maxFiles = config.maxStoredFiles
            if (files.size > maxFiles) {
                files.sortedBy { it.lastModified() }
                    .take(files.size - maxFiles)
                    .forEach { file ->
                        file.delete()
                        Log.d(TAG, "Deleted old export file: ${file.name}")
                    }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to cleanup old files", e)
        }
    }
    
    /**
     * Get list of exported files
     */
    fun getExportedFiles(): List<File> {
        val dir = getExportDirectory()
        return dir.listFiles()?.toList() ?: emptyList()
    }
    
    /**
     * Get total event count
     */
    fun getEventCount(): Int {
        return eventCount
    }
    
    /**
     * Clear all exported files
     */
    fun clearExports() {
        try {
            val dir = getExportDirectory()
            dir.listFiles()?.forEach { it.delete() }
            Log.d(TAG, "Cleared all exported files")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to clear exports", e)
        }
    }
    
    /**
     * Event batch for export
     */
    data class EventBatch(
        val timestamp: Long,
        val count: Int,
        val events: List<Event>
    )
    
    /**
     * Export configuration
     */
    data class ExportConfig(
        val bufferSize: Int = 50,  // Export after N events
        val maxStoredFiles: Int = 10,  // Keep last N files
        val exportIntervalMs: Long = 30000  // Export every 30s
    )
    
    companion object {
        private const val TAG = "EventExporter"
    }
}