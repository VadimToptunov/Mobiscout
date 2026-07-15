//
//  HierarchyCollector.swift
//  MobiscoutSDK
//
//  Captures UI hierarchy snapshots
//

import Foundation
import UIKit
import SwiftUI

/// Captures and serializes UI view hierarchy
public class HierarchyCollector {
    
    // MARK: - Properties
    
    private let eventBus: EventBus
    private var isCollecting = false
    
    // MARK: - Initializer
    
    public init(eventBus: EventBus) {
        self.eventBus = eventBus
    }
    
    // MARK: - Public API
    
    /// Start hierarchy collection
    public func start() {
        guard !isCollecting else {
            print("[HierarchyCollector] Already collecting")
            return
        }
        
        print("[HierarchyCollector] Starting...")
        isCollecting = true
        print("[HierarchyCollector] Started")
    }
    
    /// Stop hierarchy collection
    public func stop() {
        guard isCollecting else {
            print("[HierarchyCollector] Not collecting")
            return
        }
        
        print("[HierarchyCollector] Stopping...")
        isCollecting = false
        print("[HierarchyCollector] Stopped")
    }
    
    /// Capture current UI hierarchy
    /// - Parameters:
    ///   - screen: Screen identifier
    ///   - rootView: Root view to start traversal from
    public func captureHierarchy(screen: String, rootView: UIView? = nil) {
        guard isCollecting else { return }
        
        let timestamp = Int64(Date().timeIntervalSince1970 * 1000)
        let sessionId = MobiscoutSDK.shared.getSession()?.sessionId ?? "unknown"
        
        // Get root view
        let root = rootView ?? UIApplication.shared.keyWindow?.rootViewController?.view
        
        guard let rootView = root else {
            print("[HierarchyCollector] No root view available")
            return
        }
        
        // Traverse and serialize hierarchy
        let hierarchyDict = traverseView(rootView)
        
        guard let jsonData = try? JSONSerialization.data(withJSONObject: hierarchyDict, options: [.prettyPrinted]),
              let jsonString = String(data: jsonData, encoding: .utf8) else {
            print("[HierarchyCollector] Failed to serialize hierarchy")
            return
        }
        
        let event = HierarchyEvent(
            timestamp: timestamp,
            sessionId: sessionId,
            screen: screen,
            hierarchy: jsonString
        )
        
        eventBus.publish(event)
        print("[HierarchyCollector] Captured hierarchy for screen: \(screen)")
    }
    
    // MARK: - Private Methods
    
    /// Recursively traverse view hierarchy
    /// - Parameter view: View to traverse
    /// - Returns: Dictionary representation of view
    private func traverseView(_ view: UIView) -> [String: Any] {
        var viewDict: [String: Any] = [:]
        
        // Basic attributes
        viewDict["class"] = String(describing: type(of: view))
        viewDict["accessibilityIdentifier"] = view.accessibilityIdentifier ?? NSNull()
        viewDict["accessibilityLabel"] = view.accessibilityLabel ?? NSNull()
        viewDict["isUserInteractionEnabled"] = view.isUserInteractionEnabled
        viewDict["isHidden"] = view.isHidden
        
        // Frame and bounds
        let frame = view.frame
        viewDict["frame"] = [
            "x": frame.origin.x,
            "y": frame.origin.y,
            "width": frame.size.width,
            "height": frame.size.height
        ]
        
        // Type-specific attributes
        if let label = view as? UILabel {
            viewDict["text"] = label.text ?? NSNull()
        } else if let button = view as? UIButton {
            viewDict["title"] = button.titleLabel?.text ?? NSNull()
        } else if let textField = view as? UITextField {
            viewDict["placeholder"] = textField.placeholder ?? NSNull()
            viewDict["text"] = textField.text ?? NSNull()
        } else if let imageView = view as? UIImageView {
            viewDict["hasImage"] = imageView.image != nil
        }
        
        // Traverse children
        if !view.subviews.isEmpty {
            viewDict["children"] = view.subviews.map { traverseView($0) }
        }
        
        return viewDict
    }
}

