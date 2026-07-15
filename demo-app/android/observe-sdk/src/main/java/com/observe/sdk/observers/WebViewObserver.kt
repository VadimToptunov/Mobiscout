package com.mobiscout.sdk.observers

import android.content.Context
import android.os.Build
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebView
import androidx.annotation.RequiresApi
import com.mobiscout.sdk.MobiscoutSDK
import com.mobiscout.sdk.events.Event
import com.mobiscout.sdk.events.EventBus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Mobiscouts WebView interactions and DOM elements
 * 
 * Captures:
 * - Page loads
 * - DOM element clicks
 * - Form inputs
 * - Form submissions
 * - Navigation events
 * - Element hierarchy (similar to native)
 */
class WebViewMobiscoutr(
    private val context: Context,
    private val eventBus: EventBus
) {
    
    companion object {
        private const val TAG = "WebViewMobiscoutr"
        private const val JS_INTERFACE_NAME = "MobiscoutSDK"
        
        // JavaScript injection for observing web interactions
        // Note: Using trimIndent() and string interpolation with ${} for proper variable substitution
        private val INJECTION_SCRIPT = """
            (function() {
                console.log('[MobiscoutSDK] Injecting WebView observer...');
                
                // Capture click events
                document.addEventListener('click', function(e) {
                    var target = e.target;
                    var selectors = getAllSelectors(target);
                    var data = {
                        eventType: 'click',
                        tag: target.tagName.toLowerCase(),
                        id: target.id || null,
                        className: target.className || null,
                        text: target.innerText ? target.innerText.substring(0, 100) : null,
                        value: target.value || null,
                        name: target.name || null,
                        href: target.href || null,
                        type: target.type || null,
                        x: e.clientX,
                        y: e.clientY,
                        xpath: selectors.xpath,
                        xpathIndexed: selectors.xpathIndexed,
                        cssSelector: selectors.cssSelector,
                        allSelectors: selectors,
                        innerHTML: target.innerHTML ? target.innerHTML.substring(0, 200) : null
                    };
                    
                    try {
                        ${JS_INTERFACE_NAME}.onWebInteraction(JSON.stringify(data));
                    } catch(e) {
                        console.error('[MobiscoutSDK] Error sending click event:', e);
                    }
                }, true);
                
                // Capture input events
                document.addEventListener('input', function(e) {
                    var target = e.target;
                    if (target.tagName.toLowerCase() === 'input' || 
                        target.tagName.toLowerCase() === 'textarea') {
                        var selectors = getAllSelectors(target);
                        var data = {
                            eventType: 'input',
                            tag: target.tagName.toLowerCase(),
                            id: target.id || null,
                            className: target.className || null,
                            name: target.name || null,
                            type: target.type || null,
                            value: target.value ? '***' : null, // Masked for security
                            xpath: selectors.xpath,
                            xpathIndexed: selectors.xpathIndexed,
                            cssSelector: selectors.cssSelector,
                            allSelectors: selectors
                        };
                        
                        try {
                            ${JS_INTERFACE_NAME}.onWebInteraction(JSON.stringify(data));
                        } catch(e) {
                            console.error('[MobiscoutSDK] Error sending input event:', e);
                        }
                    }
                }, true);
                
                // Capture form submissions
                document.addEventListener('submit', function(e) {
                    var form = e.target;
                    var data = {
                        eventType: 'submit',
                        tag: 'form',
                        id: form.id || null,
                        className: form.className || null,
                        action: form.action || null,
                        method: form.method || null,
                        xpath: getXPath(form),
                        cssSelector: getCSSSelector(form)
                    };
                    
                    try {
                        ${JS_INTERFACE_NAME}.onWebInteraction(JSON.stringify(data));
                    } catch(e) {
                        console.error('[MobiscoutSDK] Error sending submit event:', e);
                    }
                }, true);
                
                // Helper: Get XPath of element
                function getXPath(element) {
                    if (element.id) {
                        return '//*[@id="' + element.id + '"]';
                    }
                    
                    if (element === document.body) {
                        return '/html/body';
                    }
                    
                    var ix = 0;
                    var siblings = element.parentNode.childNodes;
                    for (var i = 0; i < siblings.length; i++) {
                        var sibling = siblings[i];
                        if (sibling === element) {
                            var parentPath = getXPath(element.parentNode);
                            return parentPath + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                        }
                        if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                            ix++;
                        }
                    }
                }
                
                // Helper: Get unique CSS Selector with fallback strategies
                function getCSSSelector(element) {
                    // Strategy 1: ID (most reliable)
                    if (element.id) {
                        return '#' + element.id;
                    }
                    
                    // Strategy 2: name attribute (for forms)
                    if (element.name) {
                        var nameSelector = element.tagName.toLowerCase() + '[name="' + element.name + '"]';
                        if (document.querySelectorAll(nameSelector).length === 1) {
                            return nameSelector;
                        }
                    }
                    
                    // Strategy 3: Unique combination of tag + classes
                    if (element.className) {
                        var classes = element.className.split(/\s+/).filter(c => c.length > 0);
                        if (classes.length > 0) {
                            var classSelector = element.tagName.toLowerCase() + '.' + classes.join('.');
                            if (document.querySelectorAll(classSelector).length === 1) {
                                return classSelector;
                            }
                        }
                    }
                    
                    // Strategy 4: Tag + text content (for buttons/links)
                    // SKIPPED: :contains() is not standard CSS selector
                    // Text-based selection is handled via XPath strategies instead
                    // Example: button:contains("Submit") -> use XPath //button[text()="Submit"]
                    
                    // Strategy 5: nth-child with parent context
                    var parent = element.parentNode;
                    if (parent) {
                        var index = Array.from(parent.children).indexOf(element) + 1;
                        var parentSelector = parent.id ? '#' + parent.id : parent.tagName.toLowerCase();
                        return parentSelector + ' > ' + element.tagName.toLowerCase() + ':nth-child(' + index + ')';
                    }
                    
                    // Fallback: just tag name
                    return element.tagName.toLowerCase();
                }
                
                // Helper: Get unique XPath with multiple strategies
                function getUniqueXPath(element) {
                    // Strategy 1: ID-based
                    if (element.id) {
                        return '//*[@id="' + element.id + '"]';
                    }
                    
                    // Strategy 2: Name attribute
                    if (element.name) {
                        var xpath = '//' + element.tagName.toLowerCase() + '[@name="' + element.name + '"]';
                        try {
                            if (document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null).snapshotLength === 1) {
                                return xpath;
                            }
                        } catch(e) {}
                    }
                    
                    // Strategy 3: Text content
                    if (element.innerText && element.innerText.length > 0 && element.innerText.length < 100) {
                        var text = element.innerText.trim().replace(/"/g, '\\"');
                        var xpath = '//' + element.tagName.toLowerCase() + '[text()="' + text + '"]';
                        try {
                            if (document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null).snapshotLength === 1) {
                                return xpath;
                            }
                            // Try contains for partial match
                            xpath = '//' + element.tagName.toLowerCase() + '[contains(text(),"' + text + '")]';
                            if (document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null).snapshotLength === 1) {
                                return xpath;
                            }
                        } catch(e) {}
                    }
                    
                    // Strategy 4: Class-based
                    if (element.className) {
                        var classes = element.className.split(/\s+/).filter(c => c.length > 0);
                        if (classes.length > 0) {
                            var classXPath = '//' + element.tagName.toLowerCase();
                            for (var i = 0; i < classes.length; i++) {
                                classXPath += '[contains(@class,"' + classes[i] + '")]';
                            }
                            try {
                                if (document.evaluate(classXPath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null).snapshotLength === 1) {
                                    return classXPath;
                                }
                            } catch(e) {}
                        }
                    }
                    
                    // Strategy 5: Indexed path (fallback)
                    return getXPath(element);
                }
                
                // Helper: Get all possible selectors for an element
                function getAllSelectors(element) {
                    return {
                        xpath: getUniqueXPath(element),
                        xpathIndexed: getXPath(element),
                        cssSelector: getCSSSelector(element),
                        id: element.id || null,
                        name: element.name || null,
                        className: element.className || null,
                        tagName: element.tagName.toLowerCase()
                    };
                }
                
                // Capture page hierarchy (like HierarchyCollector)
                function captureHierarchy() {
                    var elements = [];
                    
                    function traverse(node, depth) {
                        if (depth > 10) return; // Max depth
                        
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            var rect = node.getBoundingClientRect();
                            
                            elements.push({
                                tag: node.tagName.toLowerCase(),
                                id: node.id || null,
                                className: node.className || null,
                                text: node.innerText ? node.innerText.substring(0, 100) : null,
                                value: node.value || null,
                                name: node.name || null,
                                type: node.type || null,
                                href: node.href || null,
                                clickable: node.onclick != null || node.tagName === 'A' || node.tagName === 'BUTTON',
                                depth: depth,
                                bounds: {
                                    x: Math.round(rect.x),
                                    y: Math.round(rect.y),
                                    width: Math.round(rect.width),
                                    height: Math.round(rect.height)
                                },
                                xpath: getXPath(node),
                                cssSelector: getCSSSelector(node)
                            });
                        }
                        
                        for (var i = 0; i < node.childNodes.length; i++) {
                            traverse(node.childNodes[i], depth + 1);
                        }
                    }
                    
                    traverse(document.body, 0);
                    
                    return {
                        url: window.location.href,
                        title: document.title,
                        totalElements: elements.length,
                        elements: elements
                    };
                }
                
                // Notify SDK that page loaded
                document.addEventListener('DOMContentLoaded', function() {
                    try {
                        var hierarchy = captureHierarchy();
                        ${JS_INTERFACE_NAME}.onPageLoad(window.location.href, JSON.stringify(hierarchy));
                    } catch(e) {
                        console.error('[MobiscoutSDK] Error capturing hierarchy:', e);
                    }
                });
                
                // If DOM already loaded
                if (document.readyState === 'complete' || document.readyState === 'interactive') {
                    try {
                        var hierarchy = captureHierarchy();
                        ${JS_INTERFACE_NAME}.onPageLoad(window.location.href, JSON.stringify(hierarchy));
                    } catch(e) {
                        console.error('[MobiscoutSDK] Error capturing hierarchy:', e);
                    }
                }
                
                console.log('[MobiscoutSDK] WebView observer injected successfully');
            })();
        """.trimIndent()
    }
    
    // Coroutine scope for async event publishing
    // Recreated on each start() to allow stop/start cycles
    private var scope: CoroutineScope? = null
    private var isStarted = false
    private val observedWebViews = mutableSetOf<WebView>()
    
    fun start() {
        if (isStarted) {
            Log.w(TAG, "WebViewMobiscoutr already started")
            return
        }
        
        // Create new coroutine scope for this start/stop cycle
        // This allows stop() → start() sequences to work correctly
        scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        
        isStarted = true
        Log.d(TAG, "WebViewMobiscoutr started with new coroutine scope")
        
        // Enable WebView debugging (for Chrome DevTools)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            WebView.setWebContentsDebuggingEnabled(true)
        }
    }
    
    fun stop() {
        if (!isStarted) return
        
        isStarted = false
        observedWebViews.clear()
        
        // Cancel the coroutine scope to prevent memory leaks
        // All launched coroutines will be cancelled and won't access deallocated WebViews
        scope?.cancel()
        scope = null  // Set to null so it can be recreated on next start()
        
        Log.d(TAG, "WebViewMobiscoutr stopped and coroutine scope cancelled")
    }
    
    /**
     * Register a WebView for observation
     * Call this when WebView is created
     */
    fun observeWebView(webView: WebView, screenName: String) {
        if (!isStarted) {
            Log.w(TAG, "WebViewMobiscoutr not started, cannot mobiscout WebView")
            return
        }
        
        if (observedWebViews.contains(webView)) {
            Log.d(TAG, "WebView already observed")
            return
        }
        
        observedWebViews.add(webView)
        
        // Enable JavaScript (required for injection)
        webView.settings.javaScriptEnabled = true
        
        // Add JavaScript interface
        webView.addJavascriptInterface(
            WebViewJSInterface(screenName),
            JS_INTERFACE_NAME
        )
        
        // Store the original WebViewClient
        val originalClient = webView.webViewClient
        
        // Create a delegating WebViewClient that preserves original behavior
        webView.webViewClient = object : android.webkit.WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                // Call original client first
                originalClient?.onPageFinished(view, url)
                
                url?.let {
                    Log.d(TAG, "Page finished loading: $it")
                    
                    // Inject observer script
                    webView.evaluateJavascript(INJECTION_SCRIPT) { result ->
                        Log.d(TAG, "Mobiscoutr script injected, result: $result")
                    }
                    
                    // Emit page load event
                    // Check if observer is still started before publishing
                    if (isStarted) {
                        scope?.launch {
                            eventBus.publish(
                                Event.WebViewEvent(
                                    timestamp = System.currentTimeMillis(),
                                    sessionId = MobiscoutSDK.getSession()?.sessionId ?: "",
                                    screen = screenName,
                                    url = it,
                                    eventType = "page_load",
                                    elementSelector = null,
                                    elementTag = null,
                                    elementText = null,
                                    elementValue = null,
                                    elementAttributes = null,
                                    x = null,
                                    y = null,
                                    innerHTML = null
                                )
                            )
                        }
                    }
                }
            }
            
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                return originalClient?.shouldOverrideUrlLoading(view, url) ?: super.shouldOverrideUrlLoading(view, url)
            }
            
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                originalClient?.onPageStarted(view, url, favicon) ?: super.onPageStarted(view, url, favicon)
            }
            
            // Delegate error handling methods
            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                originalClient?.onReceivedError(view, errorCode, description, failingUrl) 
                    ?: super.onReceivedError(view, errorCode, description, failingUrl)
            }
            
            @android.annotation.TargetApi(android.os.Build.VERSION_CODES.M)
            override fun onReceivedError(
                view: WebView?,
                request: android.webkit.WebResourceRequest?,
                error: android.webkit.WebResourceError?
            ) {
                originalClient?.onReceivedError(view, request, error) 
                    ?: super.onReceivedError(view, request, error)
            }
            
            override fun onReceivedHttpError(
                view: WebView?,
                request: android.webkit.WebResourceRequest?,
                errorResponse: android.webkit.WebResourceResponse?
            ) {
                originalClient?.onReceivedHttpError(view, request, errorResponse) 
                    ?: super.onReceivedHttpError(view, request, errorResponse)
            }
            
            override fun onReceivedSslError(
                view: WebView?,
                handler: android.webkit.SslErrorHandler?,
                error: android.net.http.SslError?
            ) {
                originalClient?.onReceivedSslError(view, handler, error) 
                    ?: super.onReceivedSslError(view, handler, error)
            }
            
            // Delegate resource loading methods
            override fun onLoadResource(view: WebView?, url: String?) {
                originalClient?.onLoadResource(view, url) ?: super.onLoadResource(view, url)
            }
            
            override fun shouldInterceptRequest(view: WebView?, url: String?): android.webkit.WebResourceResponse? {
                return originalClient?.shouldInterceptRequest(view, url) 
                    ?: super.shouldInterceptRequest(view, url)
            }
            
            override fun shouldInterceptRequest(
                view: WebView?,
                request: android.webkit.WebResourceRequest?
            ): android.webkit.WebResourceResponse? {
                return originalClient?.shouldInterceptRequest(view, request) 
                    ?: super.shouldInterceptRequest(view, request)
            }
            
            // Delegate form resubmission
            override fun onFormResubmission(view: WebView?, dontResend: android.os.Message?, resend: android.os.Message?) {
                originalClient?.onFormResubmission(view, dontResend, resend) 
                    ?: super.onFormResubmission(view, dontResend, resend)
            }
            
            // Delegate authentication
            override fun onReceivedHttpAuthRequest(
                view: WebView?,
                handler: android.webkit.HttpAuthHandler?,
                host: String?,
                realm: String?
            ) {
                originalClient?.onReceivedHttpAuthRequest(view, handler, host, realm) 
                    ?: super.onReceivedHttpAuthRequest(view, handler, host, realm)
            }
            
            // Delegate client certificate request
            override fun onReceivedClientCertRequest(view: WebView?, request: android.webkit.ClientCertRequest?) {
                originalClient?.onReceivedClientCertRequest(view, request) 
                    ?: super.onReceivedClientCertRequest(view, request)
            }
            
            // Delegate scale changes
            override fun onScaleChanged(view: WebView?, oldScale: Float, newScale: Float) {
                originalClient?.onScaleChanged(view, oldScale, newScale) 
                    ?: super.onScaleChanged(view, oldScale, newScale)
            }
            
            // Delegate render process handling
            override fun onRenderProcessGone(view: WebView?, detail: android.webkit.RenderProcessGoneDetail?): Boolean {
                return originalClient?.onRenderProcessGone(view, detail) 
                    ?: super.onRenderProcessGone(view, detail)
            }
            
            // Delegate safe browsing
            @android.annotation.TargetApi(android.os.Build.VERSION_CODES.O_MR1)
            override fun onSafeBrowsingHit(
                view: WebView?,
                request: android.webkit.WebResourceRequest?,
                threatType: Int,
                callback: android.webkit.SafeBrowsingResponse?
            ) {
                originalClient?.onSafeBrowsingHit(view, request, threatType, callback) 
                    ?: super.onSafeBrowsingHit(view, request, threatType, callback)
            }
        }
        
        // Store the original client to restore later
        webView.setTag(R.id.webview_original_client_tag, originalClient)
        
        Log.d(TAG, "WebView observation enabled for screen: $screenName")
    }
    
    /**
     * Unregister a WebView from observation
     */
    fun stopObservingWebView(webView: WebView) {
        observedWebViews.remove(webView)
        
        // Remove JavaScript interface
        webView.removeJavascriptInterface(JS_INTERFACE_NAME)
        
        // Restore original WebViewClient only if it was stored
        val originalClient = webView.getTag(R.id.webview_original_client_tag) as? android.webkit.WebViewClient
        if (originalClient != null) {
            webView.webViewClient = originalClient
        }
        // If no original was stored, leave the current client as-is (don't replace with empty client)
        webView.setTag(R.id.webview_original_client_tag, null)
        
        Log.d(TAG, "WebView observation disabled - all resources cleaned up")
    }
    
    /**
     * JavaScript interface for WebView → SDK communication
     */
    inner class WebViewJSInterface(private val screenName: String) {
        
        @JavascriptInterface
        fun onWebInteraction(dataJson: String) {
            Log.d(TAG, "Web interaction: $dataJson")
            
            try {
                val json = JSONObject(dataJson)
                val eventType = json.getString("eventType")
                
                val attributes = mutableMapOf<String, String>()
                json.optString("id")?.takeIf { it.isNotEmpty() }?.let { attributes["id"] = it }
                json.optString("className")?.takeIf { it.isNotEmpty() }?.let { attributes["class"] = it }
                json.optString("name")?.takeIf { it.isNotEmpty() }?.let { attributes["name"] = it }
                json.optString("type")?.takeIf { it.isNotEmpty() }?.let { attributes["type"] = it }
                json.optString("href")?.takeIf { it.isNotEmpty() }?.let { attributes["href"] = it }
                
                // Check if observer is still started before publishing
                if (isStarted) {
                    scope?.launch {
                        eventBus.publish(
                            Event.WebViewEvent(
                                timestamp = System.currentTimeMillis(),
                                sessionId = MobiscoutSDK.getSession()?.sessionId ?: "",
                                screen = screenName,
                                url = "", // Will be set by WebViewClient
                                eventType = eventType,
                                elementSelector = json.optString("cssSelector"),
                                elementTag = json.optString("tag"),
                                elementText = json.optString("text"),
                                elementValue = json.optString("value"),
                                elementAttributes = attributes,
                                x = if (json.has("x")) json.getInt("x") else null,
                                y = if (json.has("y")) json.getInt("y") else null,
                                innerHTML = json.optString("innerHTML")
                            )
                        )
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error parsing web interaction: ${e.message}", e)
            }
        }
        
        @JavascriptInterface
        fun onPageLoad(url: String, hierarchyJson: String) {
            Log.d(TAG, "Page loaded: $url, hierarchy size: ${hierarchyJson.length}")
            
            try {
                // Emit hierarchy event (similar to HierarchyCollector)
                // Check if observer is still started before publishing
                if (isStarted) {
                    scope?.launch {
                        eventBus.publish(
                            Event.HierarchyEvent(
                                timestamp = System.currentTimeMillis(),
                                sessionId = MobiscoutSDK.getSession()?.sessionId ?: "",
                                screen = "$screenName (WebView)",
                                hierarchy = hierarchyJson
                            )
                        )
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error processing page load: ${e.message}", e)
            }
        }
    }
}

