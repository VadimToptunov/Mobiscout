package com.mobiscout.sdk

import android.app.Application
import android.util.Log
import android.webkit.WebView
import com.mobiscout.sdk.core.MobiscoutConfig
import com.mobiscout.sdk.core.MobiscoutSession
import com.mobiscout.sdk.events.Event
import com.mobiscout.sdk.events.EventBus
import com.mobiscout.sdk.export.EventExporter
import com.mobiscout.sdk.observers.NavigationMobiscoutr
import com.mobiscout.sdk.observers.NetworkMobiscoutr
import com.mobiscout.sdk.observers.UIMobiscoutr
import com.mobiscout.sdk.observers.WebViewMobiscoutr
import com.mobiscout.sdk.security.CryptoKeyExporter
import java.io.File
import java.util.UUID

/**
 * Main entry point for Mobiscout SDK
 * 
 * Usage:
 * ```kotlin
 * // In Application class
 * class MyApp : Application() {
 *     override fun onCreate() {
 *         super.onCreate()
 *         MobiscoutSDK.initialize(
 *             this,
 *             MobiscoutConfig(enabled = true)
 *         )
 *     }
 * }
 * ```
 */
object MobiscoutSDK {
    
    private var isInitialized = false
    private var isStarted = false
    
    private lateinit var application: Application
    private lateinit var config: MobiscoutConfig
    private lateinit var session: MobiscoutSession
    
    // Core components
    private lateinit var eventBus: EventBus
    private lateinit var eventExporter: EventExporter
    
    // Mobiscoutrs
    private lateinit var uiMobiscoutr: UIMobiscoutr
    private lateinit var navigationMobiscoutr: NavigationMobiscoutr
    private lateinit var networkMobiscoutr: NetworkMobiscoutr
    private lateinit var webViewMobiscoutr: WebViewMobiscoutr
    
    /**
     * Initialize SDK with configuration
     */
    fun initialize(app: Application, cfg: MobiscoutConfig) {
        if (isInitialized) {
            Log.w(TAG, "SDK already initialized")
            return
        }
        
        application = app
        config = cfg
        
        if (!config.enabled) {
            Log.i(TAG, "SDK disabled by config")
            return
        }
        
        Log.i(TAG, "Initializing MobiscoutSDK...")
        
        // Create session
        session = MobiscoutSession.create(app)
        
        // Initialize components
        eventBus = EventBus()
        eventExporter = EventExporter(
            context = app,
            config = EventExporter.ExportConfig(
                bufferSize = cfg.eventBufferSize,
                maxStoredFiles = cfg.maxStoredFiles
            )
        )
        
        // Initialize crypto key exporter if enabled
        if (cfg.exportCryptoKeys) {
            Log.w(TAG, " Crypto key export ENABLED - this build can decrypt traffic!")
            CryptoKeyExporter.initialize(cfg)
        }
        
        // Initialize observers
        uiMobiscoutr = UIMobiscoutr(app, eventBus)
        navigationMobiscoutr = NavigationMobiscoutr(app, eventBus)
        networkMobiscoutr = NetworkMobiscoutr(eventBus)
        webViewMobiscoutr = WebViewMobiscoutr(app, eventBus)
        
        // Subscribe to events
        subscribeToEvents()
        
        isInitialized = true
        
        // Auto-start if configured
        if (config.autoStart) {
            start()
        }
        
        Log.i(TAG, "SDK initialized successfully. Session: ${session.sessionId}")
    }
    
    /**
     * Start observation
     */
    fun start() {
        if (!isInitialized) {
            Log.e(TAG, "SDK not initialized. Call initialize() first.")
            return
        }
        
        if (isStarted) {
            Log.w(TAG, "SDK already started")
            return
        }
        
        Log.i(TAG, "Starting observation...")
        
        // Set flag BEFORE starting observers to prevent race conditions
        // If observers start publishing events before isStarted=true,
        // other SDK methods might reject those events
        isStarted = true
        
        // Start exporter
        eventExporter.start()
        
        // Start observers
        uiMobiscoutr.start()
        navigationMobiscoutr.start()
        networkMobiscoutr.start()
        webViewMobiscoutr.start()
        
        // Emit session start event
        eventBus.publish(Event.SessionEvent(
            timestamp = System.currentTimeMillis(),
            sessionId = session.sessionId,
            eventType = "session_start",
            data = mapOf(
                "device_model" to session.deviceModel,
                "os_version" to session.osVersion,
                "app_version" to session.appVersion
            )
        ))
        
        Log.i(TAG, "Observation started")
    }
    
    /**
     * Stop observation
     */
    fun stop() {
        if (!isStarted) {
            Log.w(TAG, "SDK not started")
            return
        }
        
        Log.i(TAG, "Stopping observation...")
        
        // Set flag BEFORE stopping observers to prevent race conditions
        // This ensures no new events are accepted while shutdown is in progress
        isStarted = false
        
        // Emit session end event
        eventBus.publish(Event.SessionEvent(
            timestamp = System.currentTimeMillis(),
            sessionId = session.sessionId,
            eventType = "session_end",
            data = mapOf(
                "duration" to (System.currentTimeMillis() - session.startTime),
                "event_count" to eventExporter.getEventCount()
            )
        ))
        
        // Stop observers
        uiMobiscoutr.stop()
        navigationMobiscoutr.stop()
        networkMobiscoutr.stop()
        webViewMobiscoutr.stop()
        
        // Stop exporter (will flush events)
        eventExporter.stop()
        
        Log.i(TAG, "Observation stopped")
    }
    
    /**
     * Subscribe to EventBus and forward to exporter
     */
    private fun subscribeToEvents() {
        eventBus.subscribe<Event.UIEvent> { event ->
            // Set session ID
            val eventWithSession = event.copy(sessionId = session.sessionId)
            eventExporter.queueEvent(eventWithSession)
            Log.d(TAG, "UI Event: ${event.actionType} on ${event.screen}")
        }
        
        eventBus.subscribe<Event.NavigationEvent> { event ->
            val eventWithSession = event.copy(sessionId = session.sessionId)
            eventExporter.queueEvent(eventWithSession)
            Log.d(TAG, "Navigation: ${event.fromScreen} -> ${event.toScreen}")
        }
        
        eventBus.subscribe<Event.NetworkEvent> { event ->
            val eventWithSession = event.copy(sessionId = session.sessionId)
            eventExporter.queueEvent(eventWithSession)
            Log.d(TAG, "Network: ${event.method} ${event.endpoint} [${event.statusCode}]")
        }
        
        eventBus.subscribe<Event.SessionEvent> { event ->
            eventExporter.queueEvent(event)
            Log.d(TAG, "Session: ${event.eventType}")
        }
    }
    
    /**
     * Get current session info
     */
    fun getSession(): MobiscoutSession? {
        return if (isInitialized) session else null
    }
    
    /**
     * Get network observer for OkHttp integration
     */
    fun getNetworkMobiscoutr(): NetworkMobiscoutr? {
        return if (isInitialized) networkMobiscoutr else null
    }
    
    /**
     * Get exported event files
     */
    fun getExportedFiles(): List<java.io.File> {
        return if (isInitialized) {
            eventExporter.getExportedFiles()
        } else {
            emptyList()
        }
    }
    
    /**
     * Clear all exported events
     */
    fun clearExports() {
        if (isInitialized) {
            eventExporter.clearExports()
        }
    }
    
    /**
     * Check if SDK is initialized
     */
    fun isInitialized(): Boolean = isInitialized
    
    /**
     * Check if observation is active
     */
    fun isRunning(): Boolean = isStarted
    
    /**
     * Get event count
     */
    fun getEventCount(): Int {
        return if (isInitialized) {
            eventExporter.getEventCount()
        } else {
            0
        }
    }
    
    /**
     * Export crypto keys for traffic decryption
     * 
     * SECURITY WARNING:
     * This exports TLS/SSL session keys and device encryption keys!
     * Only call this in test/mobiscout builds!
     * 
     * Returns: File with exported keys (JSON format)
     */
    fun exportCryptoKeys(): File? {
        if (!isInitialized) {
            Log.w(TAG, "Cannot export crypto keys - SDK not initialized")
            return null
        }
        
        if (!config.exportCryptoKeys) {
            Log.w(TAG, "Crypto key export is disabled in config")
            return null
        }
        
        Log.i(TAG, "Exporting crypto keys...")
        return CryptoKeyExporter.exportKeys(application, session.sessionId)
    }
    
    /**
     * Export TLS keys in NSS Key Log format (for Wireshark)
     * 
     * Returns: File with TLS keys in Wireshark-compatible format
     */
    fun exportTLSKeys(): File? {
        if (!isInitialized) {
            Log.w(TAG, "Cannot export TLS keys - SDK not initialized")
            return null
        }
        
        if (!config.exportCryptoKeys) {
            Log.w(TAG, "Crypto key export is disabled in config")
            return null
        }
        
        Log.i(TAG, "Exporting TLS keys (NSS format)...")
        return CryptoKeyExporter.exportNSSKeyLog(application, session.sessionId)
    }
    
    /**
     * Register a WebView for observation
     * 
     * Call this when creating a WebView to mobiscout:
     * - Page loads
     * - DOM element clicks
     * - Form inputs
     * - Form submissions
     * - Element hierarchy
     * 
     * Example:
     * ```kotlin
     * val webView = WebView(context)
     * MobiscoutSDK.observeWebView(webView, "PaymentScreen")
     * ```
     */
    fun observeWebView(webView: WebView, screenName: String) {
        if (!isInitialized) {
            Log.w(TAG, "Cannot mobiscout WebView - SDK not initialized")
            return
        }
        
        if (!isStarted) {
            Log.w(TAG, "Cannot mobiscout WebView - SDK not started")
            return
        }
        
        webViewMobiscoutr.observeWebView(webView, screenName)
    }
    
    /**
     * Stop observing a WebView
     * 
     * IMPORTANT: Cleanup always proceeds regardless of SDK state to prevent resource leaks.
     * If a WebView is deallocated after stop() is called, cleanup MUST still run to
     * remove message handlers, user scripts, and delegating WebViewClient.
     * 
     * @param webView The WebView to stop observing
     */
    fun stopObservingWebView(webView: WebView) {
        // Guard against uninitialized SDK
        // While cleanup should always proceed, we can't access lateinit property if not initialized
        if (!isInitialized) {
            Log.w(TAG, "Cannot stop observing WebView - SDK not initialized (webViewMobiscoutr not created)")
            return
        }
        
        // NO further guards - cleanup must always proceed to prevent resource leaks
        // Even if SDK is stopped, WebViews may still be deallocated and need cleanup
        webViewMobiscoutr.stopObservingWebView(webView)
    }
    
    /**
     * Get crypto key export stats
     */
    fun getCryptoKeyStats(): Map<String, Any>? {
        if (!isInitialized || !config.exportCryptoKeys) {
            return null
        }
        
        return CryptoKeyExporter.getStats()
    }
    
    private const val TAG = "MobiscoutSDK"
}