package com.mobiscout.sdk.selectors

import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.compose.ui.platform.ComposeView
import org.json.JSONObject

/**
 * Enhanced selector builder for Android native elements
 * 
 * Generates multiple selector strategies with uniqueness validation:
 * 1. Test tag / resource ID (most reliable)
 * 2. Accessibility content description
 * 3. Text content (for buttons, labels)
 * 4. View hierarchy path
 * 5. Indexed path (fallback)
 */
object SelectorBuilder {
    
    /**
     * Element selector information with multiple strategies
     */
    data class ElementSelectors(
        val resourceId: String?,
        val testTag: String?,
        val contentDescription: String?,
        val text: String?,
        val className: String,
        val viewIdPath: String,
        val hierarchyPath: String,
        val indexedPath: String,
        val bounds: Bounds?,
        val attributes: Map<String, Any?>
    ) {
        data class Bounds(
            val x: Int,
            val y: Int,
            val width: Int,
            val height: Int
        )
        
        fun toJson(): String {
            val json = JSONObject()
            json.put("resourceId", resourceId)
            json.put("testTag", testTag)
            json.put("contentDescription", contentDescription)
            json.put("text", text)
            json.put("className", className)
            json.put("viewIdPath", viewIdPath)
            json.put("hierarchyPath", hierarchyPath)
            json.put("indexedPath", indexedPath)
            if (bounds != null) {
                val boundsJson = JSONObject()
                boundsJson.put("x", bounds.x)
                boundsJson.put("y", bounds.y)
                boundsJson.put("width", bounds.width)
                boundsJson.put("height", bounds.height)
                json.put("bounds", boundsJson)
            }
            val attrsJson = JSONObject()
            attributes.forEach { (key, value) ->
                attrsJson.put(key, value)
            }
            json.put("attributes", attrsJson)
            return json.toString()
        }
        
        /**
         * Get primary selector (most reliable available)
         */
        fun getPrimarySelector(): String {
            return when {
                resourceId != null -> "id:$resourceId"
                testTag != null -> "test_tag:$testTag"
                contentDescription != null -> "content_desc:$contentDescription"
                text != null && text.length < 50 -> "text:$text"
                else -> viewIdPath
            }
        }
        
        /**
         * Get all selector strategies in priority order
         */
        fun getAllStrategies(): List<Pair<String, String>> {
            val strategies = mutableListOf<Pair<String, String>>()
            
            resourceId?.let { strategies.add("resourceId" to "id:$it") }
            testTag?.let { strategies.add("testTag" to "test_tag:$it") }
            contentDescription?.let { strategies.add("contentDescription" to "content_desc:$it") }
            text?.let { 
                if (it.length < 50) strategies.add("text" to "text:$it") 
            }
            strategies.add("viewIdPath" to viewIdPath)
            strategies.add("hierarchyPath" to hierarchyPath)
            strategies.add("indexedPath" to indexedPath)
            
            return strategies
        }
    }
    
    /**
     * Build selectors for a native Android view
     */
    fun buildSelectorsForView(view: View, rootView: View): ElementSelectors {
        val resourceId = getResourceId(view)
        val testTag = getTestTag(view)
        val contentDesc = view.contentDescription?.toString()
        val text = extractText(view)
        val className = view.javaClass.simpleName
        
        val viewPath = buildViewPath(view, rootView)
        val hierarchyPath = buildHierarchyPath(view, rootView)
        val indexedPath = buildIndexedPath(view, rootView)
        
        val bounds = ElementSelectors.Bounds(
            x = IntArray(2).also { view.getLocationOnScreen(it) }[0],
            y = IntArray(2).also { view.getLocationOnScreen(it) }[1],
            width = view.width,
            height = view.height
        )
        
        val attributes = extractAttributes(view)
        
        return ElementSelectors(
            resourceId = resourceId,
            testTag = testTag,
            contentDescription = contentDesc,
            text = text,
            className = className,
            viewIdPath = viewPath,
            hierarchyPath = hierarchyPath,
            indexedPath = indexedPath,
            bounds = bounds,
            attributes = attributes
        )
    }
    
    /**
     * Extract resource ID from view
     */
    private fun getResourceId(view: View): String? {
        return try {
            if (view.id != View.NO_ID) {
                view.resources.getResourceEntryName(view.id)
            } else null
        } catch (e: Exception) {
            null
        }
    }
    
    /**
     * Extract test tag from Compose or View
     */
    private fun getTestTag(view: View): String? {
        return try {
            // Try Compose test tag
            view.getTag(androidx.compose.ui.platform.ComposeView::class.java.hashCode())?.toString()
        } catch (e: Exception) {
            null
        }
    }
    
    /**
     * Extract text content from various view types
     */
    private fun extractText(view: View): String? {
        return when (view) {
            is TextView -> view.text?.toString()
            is Button -> view.text?.toString()
            is EditText -> view.hint?.toString() ?: view.text?.toString()
            is CheckBox -> view.text?.toString()
            is RadioButton -> view.text?.toString()
            else -> null
        }
    }
    
    /**
     * Build path using resource IDs where available
     */
    private fun buildViewPath(view: View, rootView: View): String {
        val path = mutableListOf<String>()
        var current: View? = view
        
        while (current != null && current != rootView) {
            val segment = when {
                current.id != View.NO_ID -> {
                    try {
                        val idName = current.resources.getResourceEntryName(current.id)
                        "${current.javaClass.simpleName}[@id='$idName']"
                    } catch (e: Exception) {
                        current.javaClass.simpleName
                    }
                }
                current.contentDescription != null -> {
                    "${current.javaClass.simpleName}[@content-desc='${current.contentDescription}']"
                }
                else -> current.javaClass.simpleName
            }
            path.add(0, segment)
            current = current.parent as? View
        }
        
        return "/" + path.joinToString("/")
    }
    
    /**
     * Build path using class hierarchy
     */
    private fun buildHierarchyPath(view: View, rootView: View): String {
        val path = mutableListOf<String>()
        var current: View? = view
        
        while (current != null && current != rootView) {
            path.add(0, current.javaClass.simpleName)
            current = current.parent as? View
        }
        
        return "/" + path.joinToString("/")
    }
    
    /**
     * Build indexed path (most fragile, but always works)
     */
    private fun buildIndexedPath(view: View, rootView: View): String {
        val path = mutableListOf<String>()
        var current: View? = view
        
        while (current != null && current != rootView) {
            val parent = current.parent
            val index = if (parent is ViewGroup) {
                val childCount = parent.childCount
                (0 until childCount).firstOrNull { i -> parent.getChildAt(i) == current } ?: 0
            } else 0
            
            path.add(0, "${current.javaClass.simpleName}[$index]")
            current = parent as? View
        }
        
        return "/" + path.joinToString("/")
    }
    
    /**
     * Extract all relevant attributes
     */
    private fun extractAttributes(view: View): Map<String, Any?> {
        val attrs = mutableMapOf<String, Any?>()
        
        attrs["clickable"] = view.isClickable
        attrs["enabled"] = view.isEnabled
        attrs["focusable"] = view.isFocusable
        attrs["visible"] = view.visibility == View.VISIBLE
        attrs["alpha"] = view.alpha
        
        when (view) {
            is EditText -> {
                attrs["inputType"] = view.inputType
                attrs["hint"] = view.hint?.toString()
            }
            is CheckBox -> {
                attrs["checked"] = view.isChecked
            }
            is RadioButton -> {
                attrs["checked"] = view.isChecked
            }
            is ImageView -> {
                attrs["hasImage"] = view.drawable != null
            }
        }
        
        return attrs
    }
    
    /**
     * Validate if selector is unique in the view hierarchy
     */
    fun isSelectorUnique(selector: String, rootView: View): Boolean {
        val matchCount = countMatches(selector, rootView)
        return matchCount == 1
    }
    
    /**
     * Count how many views match the given selector
     */
    private fun countMatches(selector: String, rootView: View): Int {
        // Parse selector format
        return when {
            selector.startsWith("id:") -> {
                val id = selector.removePrefix("id:")
                countByResourceId(id, rootView)
            }
            selector.startsWith("test_tag:") -> {
                val tag = selector.removePrefix("test_tag:")
                countByTestTag(tag, rootView)
            }
            selector.startsWith("content_desc:") -> {
                val desc = selector.removePrefix("content_desc:")
                countByContentDescription(desc, rootView)
            }
            selector.startsWith("text:") -> {
                val text = selector.removePrefix("text:")
                countByText(text, rootView)
            }
            selector.startsWith("/") -> {
                // Path-based selector
                countByPath(selector, rootView)
            }
            else -> 0
        }
    }
    
    /**
     * Count views with matching resource ID
     */
    private fun countByResourceId(id: String, rootView: View): Int {
        var count = 0
        traverseHierarchy(rootView) { view ->
            if (getResourceId(view) == id) {
                count++
            }
        }
        return count
    }
    
    /**
     * Count views with matching test tag
     */
    private fun countByTestTag(tag: String, rootView: View): Int {
        var count = 0
        traverseHierarchy(rootView) { view ->
            if (getTestTag(view) == tag) {
                count++
            }
        }
        return count
    }
    
    /**
     * Count views with matching content description
     */
    private fun countByContentDescription(desc: String, rootView: View): Int {
        var count = 0
        traverseHierarchy(rootView) { view ->
            if (view.contentDescription?.toString() == desc) {
                count++
            }
        }
        return count
    }
    
    /**
     * Count views with matching text
     */
    private fun countByText(text: String, rootView: View): Int {
        var count = 0
        traverseHierarchy(rootView) { view ->
            if (extractText(view) == text) {
                count++
            }
        }
        return count
    }
    
    /**
     * Count views matching a path-based selector
     */
    private fun countByPath(path: String, rootView: View): Int {
        var count = 0
        traverseHierarchy(rootView) { view ->
            val viewIdPath = buildViewPath(view, rootView)
            val hierarchyPath = buildHierarchyPath(view, rootView)
            val indexedPath = buildIndexedPath(view, rootView)
            
            if (viewIdPath == path || hierarchyPath == path || indexedPath == path) {
                count++
            }
        }
        return count
    }
    
    /**
     * Traverse view hierarchy and execute callback for each view
     */
    private fun traverseHierarchy(view: View, callback: (View) -> Unit) {
        callback(view)
        if (view is ViewGroup) {
            for (i in 0 until view.childCount) {
                traverseHierarchy(view.getChildAt(i), callback)
            }
        }
    }

}

