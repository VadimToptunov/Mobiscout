//
//  SelectorBuilder.swift
//  MobiscoutSDK
//
//  Enhanced selector builder for iOS native elements
//

import UIKit
import SwiftUI

/// Enhanced selector builder for iOS elements
/// Generates multiple selector strategies with uniqueness validation
public class SelectorBuilder {
    
    /// Element selector information with multiple strategies
    public struct ElementSelectors: Codable {
        public let accessibilityIdentifier: String?
        public let accessibilityLabel: String?
        public let text: String?
        public let className: String
        public let viewIdPath: String
        public let hierarchyPath: String
        public let indexedPath: String
        public let bounds: Bounds?
        public let attributes: [String: String]
        
        public struct Bounds: Codable {
            public let x: Double
            public let y: Double
            public let width: Double
            public let height: Double
        }
        
        /// Get primary selector (most reliable available)
        public func getPrimarySelector() -> String {
            if let accessibilityId = accessibilityIdentifier {
                return "accessibility_id:\(accessibilityId)"
            } else if let label = accessibilityLabel {
                return "accessibility_label:\(label)"
            } else if let text = text, text.count < 50 {
                return "text:\(text)"
            } else {
                return viewIdPath
            }
        }
        
        /// Get all selector strategies in priority order
        public func getAllStrategies() -> [(String, String)] {
            var strategies: [(String, String)] = []
            
            if let id = accessibilityIdentifier {
                strategies.append(("accessibilityIdentifier", "accessibility_id:\(id)"))
            }
            if let label = accessibilityLabel {
                strategies.append(("accessibilityLabel", "accessibility_label:\(label)"))
            }
            if let text = text, text.count < 50 {
                strategies.append(("text", "text:\(text)"))
            }
            strategies.append(("viewIdPath", viewIdPath))
            strategies.append(("hierarchyPath", hierarchyPath))
            strategies.append(("indexedPath", indexedPath))
            
            return strategies
        }
        
        /// Convert to JSON string
        public func toJSON() -> String? {
            let encoder = JSONEncoder()
            encoder.outputFormatting = .prettyPrinted
            guard let data = try? encoder.encode(self),
                  let json = String(data: data, encoding: .utf8) else {
                return nil
            }
            return json
        }
    }
    
    /// Build selectors for a UIView
    public static func buildSelectors(for view: UIView, in rootView: UIView) -> ElementSelectors {
        let accessibilityId = view.accessibilityIdentifier
        let accessibilityLabel = view.accessibilityLabel
        let text = extractText(from: view)
        let className = String(describing: type(of: view))
        
        let viewPath = buildViewPath(for: view, in: rootView)
        let hierarchyPath = buildHierarchyPath(for: view, in: rootView)
        let indexedPath = buildIndexedPath(for: view, in: rootView)
        
        let frame = view.frame
        let bounds = ElementSelectors.Bounds(
            x: Double(frame.origin.x),
            y: Double(frame.origin.y),
            width: Double(frame.size.width),
            height: Double(frame.size.height)
        )
        
        let attributes = extractAttributes(from: view)
        
        return ElementSelectors(
            accessibilityIdentifier: accessibilityId,
            accessibilityLabel: accessibilityLabel,
            text: text,
            className: className,
            viewIdPath: viewPath,
            hierarchyPath: hierarchyPath,
            indexedPath: indexedPath,
            bounds: bounds,
            attributes: attributes
        )
    }
    
    /// Extract text content from various view types
    private static func extractText(from view: UIView) -> String? {
        if let label = view as? UILabel {
            return label.text
        } else if let button = view as? UIButton {
            return button.titleLabel?.text ?? button.currentTitle
        } else if let textField = view as? UITextField {
            return textField.placeholder ?? textField.text
        } else if let textView = view as? UITextView {
            return textView.text
        }
        return nil
    }
    
    /// Build path using accessibility identifiers where available
    private static func buildViewPath(for view: UIView, in rootView: UIView) -> String {
        var path: [String] = []
        var current: UIView? = view
        
        while current != nil && current != rootView {
            guard let currentView = current else { break }
            
            let className = String(describing: type(of: currentView))
            let segment: String
            
            if let accessibilityId = currentView.accessibilityIdentifier {
                segment = "\(className)[@id='\(accessibilityId)']"
            } else if let label = currentView.accessibilityLabel {
                segment = "\(className)[@label='\(label)']"
            } else {
                segment = className
            }
            
            path.insert(segment, at: 0)
            current = currentView.superview
        }
        
        return "/" + path.joined(separator: "/")
    }
    
    /// Build path using class hierarchy
    private static func buildHierarchyPath(for view: UIView, in rootView: UIView) -> String {
        var path: [String] = []
        var current: UIView? = view
        
        while current != nil && current != rootView {
            guard let currentView = current else { break }
            let className = String(describing: type(of: currentView))
            path.insert(className, at: 0)
            current = currentView.superview
        }
        
        return "/" + path.joined(separator: "/")
    }
    
    /// Build indexed path (most fragile, but always works)
    private static func buildIndexedPath(for view: UIView, in rootView: UIView) -> String {
        var path: [String] = []
        var current: UIView? = view
        
        while current != nil && current != rootView {
            guard let currentView = current else { break }
            
            let className = String(describing: type(of: currentView))
            let index: Int
            
            if let superview = currentView.superview {
                index = superview.subviews.firstIndex(of: currentView) ?? 0
            } else {
                index = 0
            }
            
            path.insert("\(className)[\(index)]", at: 0)
            current = currentView.superview
        }
        
        return "/" + path.joined(separator: "/")
    }
    
    /// Extract all relevant attributes
    private static func extractAttributes(from view: UIView) -> [String: String] {
        var attrs: [String: String] = [:]
        
        attrs["isUserInteractionEnabled"] = String(view.isUserInteractionEnabled)
        attrs["isHidden"] = String(view.isHidden)
        attrs["alpha"] = String(view.alpha)
        attrs["isAccessibilityElement"] = String(view.isAccessibilityElement)
        
        // Type-specific attributes
        if let button = view as? UIButton {
            attrs["isEnabled"] = String(button.isEnabled)
            attrs["isSelected"] = String(button.isSelected)
        } else if let textField = view as? UITextField {
            if let placeholder = textField.placeholder {
                attrs["placeholder"] = placeholder
            }
            attrs["isSecureTextEntry"] = String(textField.isSecureTextEntry)
        } else if let switchControl = view as? UISwitch {
            attrs["isOn"] = String(switchControl.isOn)
        } else if let slider = view as? UISlider {
            attrs["value"] = String(slider.value)
            attrs["minimumValue"] = String(slider.minimumValue)
            attrs["maximumValue"] = String(slider.maximumValue)
        }
        
        return attrs
    }
    
    /// Validate if selector is unique in the view hierarchy
    public static func isSelectorUnique(_ selector: String, in rootView: UIView) -> Bool {
        let matchCount = countMatches(for: selector, in: rootView)
        return matchCount == 1
    }
    
    /// Count how many views match the given selector
    private static func countMatches(for selector: String, in rootView: UIView) -> Int {
        // Parse selector format
        if selector.hasPrefix("accessibility_id:") {
            let id = String(selector.dropFirst("accessibility_id:".count))
            return countByAccessibilityId(id, in: rootView)
        } else if selector.hasPrefix("accessibility_label:") {
            let label = String(selector.dropFirst("accessibility_label:".count))
            return countByAccessibilityLabel(label, in: rootView)
        } else if selector.hasPrefix("text:") {
            let text = String(selector.dropFirst("text:".count))
            return countByText(text, in: rootView)
        } else if selector.hasPrefix("/") {
            // Path-based selector (viewIdPath, hierarchyPath, or indexedPath)
            return countByPath(selector, in: rootView)
        } else {
            // Unknown format
            return 0
        }
    }
    
    /// Count views with matching accessibility identifier
    private static func countByAccessibilityId(_ id: String, in rootView: UIView) -> Int {
        var count = 0
        traverseHierarchy(rootView) { view in
            if view.accessibilityIdentifier == id {
                count += 1
            }
        }
        return count
    }
    
    /// Count views with matching accessibility label
    private static func countByAccessibilityLabel(_ label: String, in rootView: UIView) -> Int {
        var count = 0
        traverseHierarchy(rootView) { view in
            if view.accessibilityLabel == label {
                count += 1
            }
        }
        return count
    }
    
    /// Count views with matching text content
    private static func countByText(_ text: String, in rootView: UIView) -> Int {
        var count = 0
        traverseHierarchy(rootView) { view in
            if let viewText = extractText(from: view), viewText == text {
                count += 1
            }
        }
        return count
    }
    
    /// Count views matching a path-based selector
    private static func countByPath(_ path: String, in rootView: UIView) -> Int {
        var count = 0
        traverseHierarchy(rootView) { view in
            let viewIdPath = buildViewPath(for: view, in: rootView)
            let hierarchyPath = buildHierarchyPath(for: view, in: rootView)
            let indexedPath = buildIndexedPath(for: view, in: rootView)
            
            if viewIdPath == path || hierarchyPath == path || indexedPath == path {
                count += 1
            }
        }
        return count
    }
    
    /// Traverse view hierarchy and execute callback for each view
    private static func traverseHierarchy(_ view: UIView, callback: (UIView) -> Void) {
        callback(view)
        for subview in view.subviews {
            traverseHierarchy(subview, callback: callback)
        }
    }

}

// MARK: - SwiftUI Support

extension SelectorBuilder {
    
    /// Build selectors for SwiftUI views (when accessible via UIHostingController)
    public static func buildSelectorsForSwiftUI(identifier: String?, label: String?, text: String?) -> ElementSelectors {
        let viewPath = identifier != nil ? "/SwiftUI[@id='\(identifier!)']" : "/SwiftUI"
        let hierarchyPath = "/SwiftUI/View"
        let indexedPath = "/SwiftUI[0]/View[0]"
        
        var attributes: [String: String] = [:]
        attributes["framework"] = "SwiftUI"
        
        return ElementSelectors(
            accessibilityIdentifier: identifier,
            accessibilityLabel: label,
            text: text,
            className: "SwiftUIView",
            viewIdPath: viewPath,
            hierarchyPath: hierarchyPath,
            indexedPath: indexedPath,
            bounds: nil,
            attributes: attributes
        )
    }
}

