//
//  MobiscoutSession.swift
//  MobiscoutSDK
//
//  Represents an observation session
//

import Foundation
import UIKit

/// Represents a single observation session
public struct MobiscoutSession: Codable {
    
    /// Unique session identifier
    public let sessionId: String
    
    /// Session start timestamp
    public let startTime: Int64
    
    /// App version
    public let appVersion: String
    
    /// Platform (always "ios")
    public let platform: String
    
    /// Device information
    public let deviceInfo: DeviceInfo
    
    /// Number of events exported in this session
    public var eventsExported: Int
    
    // MARK: - Nested Types
    
    public struct DeviceInfo: Codable {
        public let model: String
        public let osVersion: String
        public let screenWidth: Int
        public let screenHeight: Int
        public let locale: String
        
        public init(
            model: String,
            osVersion: String,
            screenWidth: Int,
            screenHeight: Int,
            locale: String
        ) {
            self.model = model
            self.osVersion = osVersion
            self.screenWidth = screenWidth
            self.screenHeight = screenHeight
            self.locale = locale
        }
    }
    
    // MARK: - Initializer
    
    public init(
        sessionId: String,
        startTime: Int64,
        appVersion: String,
        platform: String,
        deviceInfo: DeviceInfo,
        eventsExported: Int = 0
    ) {
        self.sessionId = sessionId
        self.startTime = startTime
        self.appVersion = appVersion
        self.platform = platform
        self.deviceInfo = deviceInfo
        self.eventsExported = eventsExported
    }
    
    // MARK: - Factory
    
    /// Create a new session with current device info
    public static func create(appVersion: String = "1.0.0") -> MobiscoutSession {
        let device = UIDevice.current
        let screen = UIScreen.main.bounds
        
        let deviceInfo = DeviceInfo(
            model: device.model,
            osVersion: device.systemVersion,
            screenWidth: Int(screen.width),
            screenHeight: Int(screen.height),
            locale: Locale.current.identifier
        )
        
        return MobiscoutSession(
            sessionId: UUID().uuidString,
            startTime: Int64(Date().timeIntervalSince1970 * 1000),
            appVersion: appVersion,
            platform: "ios",
            deviceInfo: deviceInfo,
            eventsExported: 0
        )
    }
}

