//
//  UIMobiscoutr.swift
//  MobiscoutSDK
//
//  Mobiscouts UI interactions (taps, swipes, inputs)
//

import Foundation
import UIKit
import SwiftUI

/// Mobiscouts user interactions with UI elements
public class UIMobiscoutr {
    
    // MARK: - Properties
    
    private let eventBus: EventBus
    private var isObserving = false
    private var currentScreen: String = "Unknown"
    
    // MARK: - Initializer
    
    public init(eventBus: EventBus) {
        self.eventBus = eventBus
    }
    
    // MARK: - Public API
    
    /// Start observing UI interactions
    public func start() {
        guard !isObserving else {
            print("[UIMobiscoutr] Already observing")
            return
        }
        
        print("[UIMobiscoutr] Starting...")
        isObserving = true
        
        // Swizzle UIControl action methods
        swizzleUIControlMethods()
        
        // Swizzle UIGestureRecognizer methods
        swizzleGestureRecognizerMethods()
        
        // Swizzle UITextField methods
        swizzleTextFieldMethods()
        
        print("[UIMobiscoutr] Started")
    }
    
    /// Stop observing
    public func stop() {
        guard isObserving else {
            print("[UIMobiscoutr] Not observing")
            return
        }
        
        print("[UIMobiscoutr] Stopping...")
        isObserving = false
        print("[UIMobiscoutr] Stopped")
    }
    
    /// Set current screen name
    /// - Parameter screen: Screen identifier
    public func setCurrentScreen(_ screen: String) {
        currentScreen = screen
    }
    
    // MARK: - Event Generation
    
    /// Generate a UI event
    /// - Parameters:
    ///   - view: The view that was interacted with
    ///   - action: Action type (tap, swipe, input, etc.)
    ///   - inputText: Optional text input
    internal func generateUIEvent(
        for view: UIView,
        action: String,
        inputText: String? = nil
    ) {
        guard isObserving else { return }
        
        let timestamp = Int64(Date().timeIntervalSince1970 * 1000)
        let sessionId = MobiscoutSDK.shared.getSession()?.sessionId ?? "unknown"
        
        let elementId = view.accessibilityIdentifier
        let elementType = String(describing: type(of: view))
        let bounds = view.frame
        
        let event = UIEvent(
            timestamp: timestamp,
            sessionId: sessionId,
            screen: currentScreen,
            elementId: elementId,
            elementType: elementType,
            action: action,
            inputText: inputText,
            bounds: UIEvent.Bounds(
                x: Double(bounds.origin.x),
                y: Double(bounds.origin.y),
                width: Double(bounds.size.width),
                height: Double(bounds.size.height)
            )
        )
        
        eventBus.publish(event)
        print("[UIMobiscoutr] Event: \(action) on \(elementType) (id: \(elementId ?? "nil"))")
    }
    
    // MARK: - Method Swizzling
    
    private func swizzleUIControlMethods() {
        // Swizzle UIControl.sendAction(_:to:for:)
        let originalSelector = #selector(UIControl.sendAction(_:to:for:))
        let swizzledSelector = #selector(UIControl.observed_sendAction(_:to:for:))
        
        guard let originalMethod = class_getInstanceMethod(UIControl.self, originalSelector),
              let swizzledMethod = class_getInstanceMethod(UIControl.self, swizzledSelector) else {
            return
        }
        
        method_exchangeImplementations(originalMethod, swizzledMethod)
    }
    
    private func swizzleGestureRecognizerMethods() {
        // Swizzle UIGestureRecognizer state changes
        // Implementation similar to Android's touch event handling
    }
    
    private func swizzleTextFieldMethods() {
        // Swizzle UITextField text changes
        // Track input events
    }
}

// MARK: - UIControl Extension (Swizzled)

extension UIControl {
    
    @objc dynamic func observed_sendAction(_ action: Selector, to target: Any?, for event: UIEvent?) {
        // Call original implementation
        self.observed_sendAction(action, to: target, for: event)
        
        // Capture event if observing
        if let observer = MobiscoutSDK.shared.getUIMobiscoutr() {
            observer.generateUIEvent(for: self, action: "tap")
        }
    }
}

// Note: getUIMobiscoutr() is now implemented in MobiscoutSDK.swift

