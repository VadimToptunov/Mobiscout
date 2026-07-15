package com.mobiscout.sdk.observers

import android.app.Activity
import android.view.View
import android.view.ViewGroup
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.getAllSemanticsNodes
import com.mobiscout.sdk.events.UIHierarchyEvent
import com.mobiscout.sdk.events.UIElementInfo

/**
 * Collects full UI hierarchy for analysis
 * 
 * Captures the complete UI tree when triggered, including:
 * - All visible elements
 * - Element attributes (text, contentDescription, bounds, etc.)
 * - Hierarchy relationships (parent-child)
 * - Compose semantic tree
 */
class HierarchyCollector {
    
    /**
     * Collect UI hierarchy from activity
     */
    fun collectHierarchy(activity: Activity, triggerElementId: String? = null): UIHierarchyEvent {
        val rootView = activity.window.decorView.rootView
        val elements = mutableListOf<UIElementInfo>()
        
        // Collect from View hierarchy
        collectViewHierarchy(rootView, elements, depth = 0)
        
        // Collect from Compose if present
        val composeViews = findComposeViews(rootView)
        for (composeView in composeViews) {
            collectComposeHierarchy(composeView, elements)
        }
        
        return UIHierarchyEvent(
            timestamp = System.currentTimeMillis(),
            screenName = activity.localClassName,
            triggerElementId = triggerElementId,
            elements = elements,
            totalElements = elements.size
        )
    }
    
    /**
     * Collect hierarchy from traditional View system
     */
    private fun collectViewHierarchy(
        view: View,
        elements: MutableList<UIElementInfo>,
        depth: Int,
        parentId: String? = null
    ) {
        // Skip invisible views
        if (view.visibility != View.VISIBLE) {
            return
        }
        
        // Generate unique ID for this view
        val viewId = generateViewId(view)
        
        // Extract view information
        val elementInfo = UIElementInfo(
            id = viewId,
            type = view.javaClass.simpleName,
            text = extractText(view),
            contentDescription = view.contentDescription?.toString(),
            resourceId = extractResourceId(view),
            className = view.javaClass.name,
            bounds = extractBounds(view),
            isClickable = view.isClickable,
            isEnabled = view.isEnabled,
            isFocusable = view.isFocusable,
            depth = depth,
            parentId = parentId,
            childCount = if (view is ViewGroup) view.childCount else 0
        )
        
        elements.add(elementInfo)
        
        // Recursively collect children
        if (view is ViewGroup) {
            for (i in 0 until view.childCount) {
                val child = view.getChildAt(i)
                collectViewHierarchy(child, elements, depth + 1, viewId)
            }
        }
    }
    
    /**
     * Collect hierarchy from Compose UI
     */
    private fun collectComposeHierarchy(
        composeView: ComposeView,
        elements: MutableList<UIElementInfo>
    ) {
        try {
            // Access Compose semantic tree
            val semanticsOwner = composeView.semanticsOwner ?: return
            val rootNode = semanticsOwner.rootSemanticsNode
            
            collectSemanticsNode(rootNode, elements, depth = 0, parentId = null)
        } catch (e: Exception) {
            // Compose semantics might not be available
            android.util.Log.w("HierarchyCollector", "Failed to collect Compose hierarchy: ${e.message}")
        }
    }
    
    /**
     * Collect information from Compose SemanticsNode
     */
    private fun collectSemanticsNode(
        node: SemanticsNode,
        elements: MutableList<UIElementInfo>,
        depth: Int,
        parentId: String?
    ) {
        val config = node.config
        
        // Extract semantic properties
        val text = config.getOrNull(androidx.compose.ui.semantics.SemanticsProperties.Text)
            ?.firstOrNull()?.text
        
        val contentDescription = config.getOrNull(
            androidx.compose.ui.semantics.SemanticsProperties.ContentDescription
        )?.firstOrNull()
        
        val testTag = config.getOrNull(androidx.compose.ui.semantics.SemanticsProperties.TestTag)
        
        // Generate unique ID
        val nodeId = "compose_${node.id}"
        
        // Extract bounds
        val bounds = node.boundsInRoot
        val boundsMap = mapOf(
            "left" to bounds.left.toInt(),
            "top" to bounds.top.toInt(),
            "right" to bounds.right.toInt(),
            "bottom" to bounds.bottom.toInt(),
            "width" to bounds.width.toInt(),
            "height" to bounds.height.toInt()
        )
        
        val elementInfo = UIElementInfo(
            id = nodeId,
            type = "ComposeNode",
            text = text,
            contentDescription = contentDescription,
            resourceId = testTag,
            className = "androidx.compose.ui.semantics.SemanticsNode",
            bounds = boundsMap,
            isClickable = config.contains(androidx.compose.ui.semantics.SemanticsActions.OnClick),
            isEnabled = !config.contains(androidx.compose.ui.semantics.SemanticsProperties.Disabled),
            isFocusable = config.contains(androidx.compose.ui.semantics.SemanticsActions.RequestFocus),
            depth = depth,
            parentId = parentId,
            childCount = node.children.size
        )
        
        elements.add(elementInfo)
        
        // Recursively collect children
        for (child in node.children) {
            collectSemanticsNode(child, elements, depth + 1, nodeId)
        }
    }
    
    /**
     * Find all ComposeView instances in hierarchy
     */
    private fun findComposeViews(view: View): List<ComposeView> {
        val composeViews = mutableListOf<ComposeView>()
        
        if (view is ComposeView) {
            composeViews.add(view)
        }
        
        if (view is ViewGroup) {
            for (i in 0 until view.childCount) {
                composeViews.addAll(findComposeViews(view.getChildAt(i)))
            }
        }
        
        return composeViews
    }
    
    /**
     * Generate unique ID for view
     */
    private fun generateViewId(view: View): String {
        val resourceId = extractResourceId(view)
        return if (resourceId != null) {
            "view_$resourceId"
        } else {
            "view_${view.hashCode()}"
        }
    }
    
    /**
     * Extract text from view (handles TextView, Button, EditText, etc.)
     */
    private fun extractText(view: View): String? {
        return try {
            when (view) {
                is android.widget.TextView -> view.text?.toString()
                is android.widget.Button -> view.text?.toString()
                is android.widget.EditText -> view.text?.toString()
                else -> null
            }
        } catch (e: Exception) {
            null
        }
    }
    
    /**
     * Extract resource ID name
     */
    private fun extractResourceId(view: View): String? {
        return try {
            if (view.id != View.NO_ID) {
                view.resources.getResourceEntryName(view.id)
            } else {
                null
            }
        } catch (e: Exception) {
            null
        }
    }
    
    /**
     * Extract view bounds
     */
    private fun extractBounds(view: View): Map<String, Int> {
        val location = IntArray(2)
        view.getLocationOnScreen(location)
        
        return mapOf(
            "left" to location[0],
            "top" to location[1],
            "right" to location[0] + view.width,
            "bottom" to location[1] + view.height,
            "width" to view.width,
            "height" to view.height
        )
    }
}

