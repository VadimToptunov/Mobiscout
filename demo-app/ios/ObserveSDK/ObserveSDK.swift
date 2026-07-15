//
//  MobiscoutSDK.swift
//  MobiscoutSDK
//
//  Main entry point for iOS Mobiscout SDK
//

import Foundation
import UIKit
import SwiftUI
import WebKit

/// Main SDK class for observing app behavior
public class MobiscoutSDK {
    
    // MARK: - Singleton
    
    public static let shared = MobiscoutSDK()
    
    private init() {}
    
    // MARK: - Properties
    
    private var isInitializedFlag = false
    private var isStarted = false
    
    private var application: UIApplication?
    private var config: MobiscoutConfig?
    private var session: MobiscoutSession?
    
    private var eventBus: EventBus?
    private var eventExporter: EventExporter?
    
    private var uiMobiscoutr: UIMobiscoutr?
    private var navigationMobiscoutr: NavigationMobiscoutr?
    private var networkMobiscoutr: NetworkMobiscoutr?
    private var hierarchyCollector: HierarchyCollector?
    private var webViewMobiscoutr: WebViewMobiscoutr?
    
    // MARK: - Public API
    
    /// Initialize the Mobiscout SDK
    /// - Parameters:
    ///   - application: UIApplication instance
    ///   - config: Configuration for the SDK
    public func initialize(application: UIApplication, config: MobiscoutConfig) {
        guard !isInitializedFlag else {
            print("[MobiscoutSDK] Already initialized")
            return
        }
        
        self.application = application
        self.config = config
        
        // Mark as initialized before checking enabled flag
        isInitializedFlag = true
        
        guard config.enabled else {
            print("[MobiscoutSDK] Disabled by config (initialized but inactive)")
            return
        }
        
        print("[MobiscoutSDK] Initializing...")
        
        // Create session
        session = MobiscoutSession.create()
        
        // Initialize components
        eventBus = EventBus()
        eventExporter = EventExporter(config: EventExporter.ExportConfig(
            bufferSize: config.eventBufferSize,
            maxStoredFiles: config.maxStoredFiles,
            exportIntervalMs: config.flushIntervalMs
        ))
        
        // Initialize observers
        uiMobiscoutr = UIMobiscoutr(eventBus: eventBus!)
        navigationMobiscoutr = NavigationMobiscoutr(eventBus: eventBus!)
        networkMobiscoutr = NetworkMobiscoutr(eventBus: eventBus!)
        hierarchyCollector = HierarchyCollector(eventBus: eventBus!)
        webViewMobiscoutr = WebViewMobiscoutr(eventBus: eventBus!)
        
        // Subscribe to events
        subscribeToEvents()
        
        // Auto-start if configured
        if config.autoStart {
            start()
        }
        
        print("[MobiscoutSDK] Initialized successfully. Session: \(session?.sessionId ?? "unknown")")
    }
    
    /// Start observing
    public func start() {
        guard isInitializedFlag else {
            print("[MobiscoutSDK] Cannot start - not initialized")
            return
        }
        
        guard !isStarted else {
            print("[MobiscoutSDK] Already started")
            return
        }
        
        guard config?.enabled == true else {
            print("[MobiscoutSDK] Cannot start - disabled by config")
            return
        }
        
        print("[MobiscoutSDK] Starting observation...")
        
        isStarted = true
        
        // Start components
        eventExporter?.start()
        uiMobiscoutr?.start()
        navigationMobiscoutr?.start()
        networkMobiscoutr?.start()
        hierarchyCollector?.start()
        webViewMobiscoutr?.start()
        
        print("[MobiscoutSDK] Started")
    }
    
    /// Stop observing
    public func stop() {
        guard isStarted else {
            print("[MobiscoutSDK] Not started")
            return
        }
        
        print("[MobiscoutSDK] Stopping...")
        
        // Stop observers first
        uiMobiscoutr?.stop()
        navigationMobiscoutr?.stop()
        networkMobiscoutr?.stop()
        hierarchyCollector?.stop()
        webViewMobiscoutr?.stop()
        
        // Stop exporter (will flush remaining events)
        eventExporter?.stop()
        
        isStarted = false
        
        print("[MobiscoutSDK] Stopped")
    }
    
    /// Shutdown SDK completely
    public func shutdown() {
        stop()
        
        // Clear all components
        uiMobiscoutr = nil
        navigationMobiscoutr = nil
        networkMobiscoutr = nil
        hierarchyCollector = nil
        webViewMobiscoutr = nil
        eventExporter = nil
        eventBus = nil
        
        session = nil
        config = nil
        application = nil
        
        isInitializedFlag = false
        
        print("[MobiscoutSDK] Shutdown complete")
    }
    
    // MARK: - Getters
    
    public func isInitialized() -> Bool {
        return isInitializedFlag
    }
    
    public func isRunning() -> Bool {
        return isStarted
    }
    
    public func getSession() -> MobiscoutSession? {
        return session
    }
    
    public func getConfig() -> MobiscoutConfig? {
        return config
    }
    
    public func getNetworkMobiscoutr() -> NetworkMobiscoutr? {
        return networkMobiscoutr
    }
    
    public func getHierarchyCollector() -> HierarchyCollector? {
        return hierarchyCollector
    }
    
    internal func getUIMobiscoutr() -> UIMobiscoutr? {
        return uiMobiscoutr
    }
    
    // MARK: - WebView Observation
    
    /// Register a WKWebView for observation
    /// Call this when a WKWebView is displayed on screen
    /// - Parameters:
    ///   - webView: The WKWebView instance to mobiscout
    ///   - screenName: Name of the screen containing the WebView
    public func observeWebView(_ webView: WKWebView, screenName: String) {
        guard isInitializedFlag else {
            print("[MobiscoutSDK] Cannot mobiscout WebView - not initialized")
            return
        }
        
        guard config?.enabled == true else {
            print("[MobiscoutSDK] Cannot mobiscout WebView - disabled by config")
            return
        }
        
        webViewMobiscoutr?.mobiscout(webView: webView, screenName: screenName)
    }
    
    /// Stop observing a WKWebView
    /// Call this when the WebView is removed from screen
    ///
    /// IMPORTANT: Cleanup always proceeds regardless of SDK state to prevent resource leaks.
    /// If a WebView is deallocated after stop() is called, cleanup MUST still run to
    /// remove message handlers, user scripts, and delegating WKNavigationDelegate.
    ///
    /// - Parameter webView: The WKWebView instance to stop observing
    public func stopObservingWebView(_ webView: WKWebView) {
        // NO guard here - cleanup must always proceed to prevent resource leaks
        // Even if SDK is stopped, WebViews may still be deallocated and need cleanup
        webViewMobiscoutr?.stopObserving(webView: webView)
    }
    
    // MARK: - Private Methods
    
    private func subscribeToEvents() {
        guard let eventBus = eventBus, let eventExporter = eventExporter else {
            return
        }
        
        // Subscribe to all event types
        eventBus.events
            .sink { [weak eventExporter] event in
                eventExporter?.queueEvent(event)
            }
            .store(in: &cancellables)
    }
    
    private var cancellables = Set<AnyCancellable>()
}

// Import Combine for sink
import Combine

