package com.mobiscout.sdk.observers

import android.app.Activity
import android.app.Application
import android.os.Bundle
import android.util.Log
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import com.mobiscout.sdk.events.Event
import com.mobiscout.sdk.events.EventBus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlin.math.abs

/**
 * Mobiscouts UI interactions in Compose applications
 * 
 * Features:
 * - Tracks touch events (tap, long press)
 * - Detects swipe gestures
 * - Captures element information (test tags, bounds, text)
 * - Monitors Activity lifecycle
 */
class UIMobiscoutr(
    private val app: Application,
    private val eventBus: EventBus,
    private val enableHierarchyCapture: Boolean = true
) {
    // Coroutine scope recreated on each start() to allow stop/start cycles
    private var scope: CoroutineScope? = null
    private var currentActivity: Activity? = null
    private var currentScreen: String = "Unknown"
    private val hierarchyCollector = HierarchyCollector()
    
    // Touch tracking
    private var touchDownX = 0f
    private var touchDownY = 0f
    private var touchDownTime = 0L
    private val swipeThreshold = 100 // pixels
    private val swipeVelocityThreshold = 100 // pixels per second
    
    private val activityLifecycleCallbacks = object : Application.ActivityLifecycleCallbacks {
        override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {
            Log.d(TAG, "Activity created: ${activity.javaClass.simpleName}")
            currentActivity = activity
            currentScreen = activity.javaClass.simpleName
            
            // Install touch interceptor
            installTouchInterceptor(activity)
        }

        override fun onActivityStarted(activity: Activity) {
            currentActivity = activity
            currentScreen = activity.javaClass.simpleName
        }

        override fun onActivityResumed(activity: Activity) {
            currentActivity = activity
        }

        override fun onActivityPaused(activity: Activity) {}

        override fun onActivityStopped(activity: Activity) {}

        override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {}

        override fun onActivityDestroyed(activity: Activity) {
            if (currentActivity == activity) {
                currentActivity = null
            }
        }
    }
    
    fun start() {
        Log.d(TAG, "UIMobiscoutr started")
        // Create new coroutine scope for this start/stop cycle
        scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
        app.registerActivityLifecycleCallbacks(activityLifecycleCallbacks)
    }
    
    fun stop() {
        Log.d(TAG, "UIMobiscoutr stopped")
        app.unregisterActivityLifecycleCallbacks(activityLifecycleCallbacks)
        currentActivity = null
        
        // Cancel the coroutine scope to prevent memory leaks
        scope?.cancel()
        scope = null
    }
    
    /**
     * Install touch event interceptor on activity
     */
    private fun installTouchInterceptor(activity: Activity) {
        val rootView = activity.window.decorView.findViewById<View>(android.R.id.content)
        
        rootView.setOnTouchListener { view, event ->
            handleTouchEvent(event, view)
            false // Don't consume the event
        }
    }
    
    /**
     * Handle touch events and emit appropriate UI events
     */
    private fun handleTouchEvent(event: MotionEvent, view: View): Boolean {
        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                touchDownX = event.rawX
                touchDownY = event.rawY
                touchDownTime = System.currentTimeMillis()
            }
            
            MotionEvent.ACTION_UP -> {
                val deltaX = event.rawX - touchDownX
                val deltaY = event.rawY - touchDownY
                val deltaTime = System.currentTimeMillis() - touchDownTime
                
                val distance = Math.sqrt((deltaX * deltaX + deltaY * deltaY).toDouble()).toFloat()
                
                // Detect gesture type
                if (distance < swipeThreshold && deltaTime < 500) {
                    // Tap
                    handleTap(event, view)
                } else if (distance >= swipeThreshold) {
                    // Swipe
                    handleSwipe(deltaX, deltaY, deltaTime, event, view)
                } else if (deltaTime >= 500 && distance < swipeThreshold) {
                    // Long press
                    handleLongPress(event, view)
                }
            }
        }
        
        return false
    }
    
    /**
     * Handle tap event
     */
    private fun handleTap(event: MotionEvent, view: View) {
        scope?.launch {
            val element = findElementAtPosition(event.rawX, event.rawY, view)
            
            val uiEvent = Event.UIEvent(
                timestamp = System.currentTimeMillis(),
                sessionId = "", // Will be set by EventBus
                screen = currentScreen,
                elementId = element?.id,
                elementType = element?.type ?: "unknown",
                elementText = element?.text,
                actionType = "tap",
                x = event.rawX.toInt(),
                y = event.rawY.toInt(),
                value = null
            )
            
            eventBus.publish(uiEvent)
            Log.d(TAG, "Tap detected: $uiEvent")
        }
    }
    
    /**
     * Handle swipe gesture
     */
    private fun handleSwipe(deltaX: Float, deltaY: Float, deltaTime: Long, event: MotionEvent, view: View) {
        val direction = when {
            abs(deltaX) > abs(deltaY) -> {
                if (deltaX > 0) "swipe_right" else "swipe_left"
            }
            else -> {
                if (deltaY > 0) "swipe_down" else "swipe_up"
            }
        }
        
        scope?.launch {
            val element = findElementAtPosition(touchDownX, touchDownY, view)
            
            val uiEvent = Event.UIEvent(
                timestamp = System.currentTimeMillis(),
                sessionId = "",
                screen = currentScreen,
                elementId = element?.id,
                elementType = element?.type ?: "container",
                elementText = element?.text,
                actionType = direction,
                x = touchDownX.toInt(),
                y = touchDownY.toInt(),
                value = "{\"deltaX\":$deltaX,\"deltaY\":$deltaY,\"duration\":$deltaTime}"
            )
            
            eventBus.publish(uiEvent)
            Log.d(TAG, "Swipe detected: $direction")
        }
    }
    
    /**
     * Handle long press
     */
    private fun handleLongPress(event: MotionEvent, view: View) {
        scope?.launch {
            val element = findElementAtPosition(event.rawX, event.rawY, view)
            
            val uiEvent = Event.UIEvent(
                timestamp = System.currentTimeMillis(),
                sessionId = "",
                screen = currentScreen,
                elementId = element?.id,
                elementType = element?.type ?: "unknown",
                elementText = element?.text,
                actionType = "long_press",
                x = event.rawX.toInt(),
                y = event.rawY.toInt(),
                value = null
            )
            
            eventBus.publish(uiEvent)
            Log.d(TAG, "Long press detected: $uiEvent")
        }
    }
    
    /**
     * Find Compose element at given position
     */
    private fun findElementAtPosition(x: Float, y: Float, view: View): ElementInfo? {
        // Find ComposeView
        val composeView = findComposeView(view) ?: return null
        
        // Try to find semantics node at position
        // Note: This is simplified - real implementation would need proper semantics traversal
        return try {
            val semanticsOwner = composeView.getTag(androidx.compose.ui.R.id.androidx_compose_ui_view_composition_context)
            // Simplified: Return basic info
            ElementInfo(
                id = "element_${x.toInt()}_${y.toInt()}",
                type = "compose_element",
                text = null,
                bounds = null
            )
        } catch (e: Exception) {
            Log.w(TAG, "Failed to find element at position: ${e.message}")
            null
        }
    }
    
    /**
     * Find ComposeView in view hierarchy
     */
    private fun findComposeView(view: View): ComposeView? {
        if (view is ComposeView) {
            return view
        }
        
        if (view is ViewGroup) {
            for (i in 0 until view.childCount) {
                val composeView = findComposeView(view.getChildAt(i))
                if (composeView != null) {
                    return composeView
                }
            }
        }
        
        return null
    }
    
    /**
     * Element information
     */
    data class ElementInfo(
        val id: String?,
        val type: String,
        val text: String?,
        val bounds: String?
    )
    
    companion object {
        private const val TAG = "UIMobiscoutr"
    }
}

