//
//  MobiscoutConfig.swift
//  MobiscoutSDK
//
//  Configuration for Mobiscout SDK
//

import Foundation

/// Configuration for MobiscoutSDK
public struct MobiscoutConfig {
    
    /// Enable/disable SDK
    public let enabled: Bool
    
    /// Auto-start observation on initialization
    public let autoStart: Bool
    
    /// App version string
    public let appVersion: String
    
    /// Server URL for uploading events (optional)
    public let serverUrl: String?
    
    /// Number of events to buffer before export
    public let eventBufferSize: Int
    
    /// Maximum number of stored event files
    public let maxStoredFiles: Int
    
    /// Interval for flushing events (milliseconds)
    public let flushIntervalMs: Int64
    
    /// Enable network request/response capture
    public let enableNetworkCapture: Bool
    
    /// Enable UI hierarchy capture
    public let enableHierarchyCapture: Bool
    
    /// Performance mode (reduces event detail)
    public let performanceMode: Bool
    
    // MARK: - Initializer
    
    public init(
        enabled: Bool = true,
        autoStart: Bool = true,
        appVersion: String = "1.0.0",
        serverUrl: String? = nil,
        eventBufferSize: Int = 500,
        maxStoredFiles: Int = 10,
        flushIntervalMs: Int64 = 30000,
        enableNetworkCapture: Bool = true,
        enableHierarchyCapture: Bool = true,
        performanceMode: Bool = false
    ) {
        self.enabled = enabled
        self.autoStart = autoStart
        self.appVersion = appVersion
        self.serverUrl = serverUrl
        self.eventBufferSize = eventBufferSize
        self.maxStoredFiles = maxStoredFiles
        self.flushIntervalMs = flushIntervalMs
        self.enableNetworkCapture = enableNetworkCapture
        self.enableHierarchyCapture = enableHierarchyCapture
        self.performanceMode = performanceMode
    }
    
    // MARK: - Presets
    
    /// Development configuration (high detail, frequent exports)
    public static func development(appVersion: String = "dev") -> MobiscoutConfig {
        return MobiscoutConfig(
            enabled: true,
            autoStart: true,
            appVersion: appVersion,
            serverUrl: nil,
            eventBufferSize: 100,
            maxStoredFiles: 20,
            flushIntervalMs: 10000,
            enableNetworkCapture: true,
            enableHierarchyCapture: true,
            performanceMode: false
        )
    }
    
    /// Production configuration (SDK disabled)
    public static func production() -> MobiscoutConfig {
        return MobiscoutConfig(
            enabled: false,
            autoStart: false,
            appVersion: "prod",
            serverUrl: nil,
            eventBufferSize: 0,
            maxStoredFiles: 0,
            flushIntervalMs: 0,
            enableNetworkCapture: false,
            enableHierarchyCapture: false,
            performanceMode: false
        )
    }
    
    /// Test configuration (SDK disabled, for automation)
    public static func test() -> MobiscoutConfig {
        return MobiscoutConfig(
            enabled: false,
            autoStart: false,
            appVersion: "test",
            serverUrl: nil,
            eventBufferSize: 0,
            maxStoredFiles: 0,
            flushIntervalMs: 0,
            enableNetworkCapture: false,
            enableHierarchyCapture: false,
            performanceMode: false
        )
    }
}

