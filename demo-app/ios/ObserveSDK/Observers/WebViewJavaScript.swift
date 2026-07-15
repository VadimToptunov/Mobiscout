//
//  WebViewJavaScript.swift
//  MobiscoutSDK
//
//  Enhanced JavaScript injection for WebView observation
//  with multiple selector strategies and uniqueness validation
//

import Foundation

/// Enhanced JavaScript for WebView element observation
public struct WebViewJavaScript {
    
    public static let injectionScript = """
    (function() {
        const JS_INTERFACE_NAME = "observeSDK";

        // Helper: Get all relevant attributes
        function getElementAttributes(element) {
            var attrs = {};
            for (var i = 0; i < element.attributes.length; i++) {
                var attr = element.attributes[i];
                attrs[attr.name] = attr.value;
            }
            return attrs;
        }

        // Helper: Check if a selector is unique
        function isSelectorUnique(selector, type) {
            try {
                if (type === 'xpath') {
                    return document.evaluate(selector, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null).snapshotLength === 1;
                } else if (type === 'css') {
                    return document.querySelectorAll(selector).length === 1;
                }
            } catch (e) {
                console.warn('[MobiscoutSDK] Selector uniqueness check failed for', selector, e);
            }
            return false;
        }

        // Helper: Get robust XPath of element
        function getXPath(element) {
            if (!element || element.nodeType !== Node.ELEMENT_NODE) return null;

            // Strategy 1: ID
            if (element.id && isSelectorUnique('//*[@id="' + element.id + '"]', 'xpath')) {
                return '//*[@id="' + element.id + '"]';
            }

            // Strategy 2: Name attribute (if unique)
            if (element.name && isSelectorUnique('//' + element.tagName.toLowerCase() + '[@name="' + element.name + '"]', 'xpath')) {
                return '//' + element.tagName.toLowerCase() + '[@name="' + element.name + '"]';
            }

            // Strategy 3: Text content (if unique)
            if (element.innerText && element.innerText.trim().length > 0) {
                const text = element.innerText.trim().substring(0, 100);
                if (isSelectorUnique('//' + element.tagName.toLowerCase() + '[normalize-space(text())="' + text + '"]', 'xpath')) {
                    return '//' + element.tagName.toLowerCase() + '[normalize-space(text())="' + text + '"]';
                }
            }
            
            // Strategy 4: Text contains (if unique)
            if (element.innerText && element.innerText.trim().length > 0) {
                const text = element.innerText.trim().substring(0, 100);
                if (isSelectorUnique('//' + element.tagName.toLowerCase() + '[contains(normalize-space(text()),"' + text + '")]', 'xpath')) {
                    return '//' + element.tagName.toLowerCase() + '[contains(normalize-space(text()),"' + text + '")]';
                }
            }

            // Strategy 5: Class name (if unique and specific enough)
            if (element.className && element.className.trim().length > 0) {
                const classes = element.className.split(/\\s+/).filter(c => c.length > 0);
                if (classes.length > 0) {
                    const classXPath = '//' + element.tagName.toLowerCase() + '[' + classes.map(c => 'contains(@class,"' + c + '")').join(' and ') + ']';
                    if (isSelectorUnique(classXPath, 'xpath')) {
                        return classXPath;
                    }
                }
            }

            // Fallback: Indexed XPath (less stable)
            let path = [];
            for (let node = element; node && node.nodeType === Node.ELEMENT_NODE; node = node.parentNode) {
                let name = node.tagName.toLowerCase();
                if (node.id) {
                    name += '[@id="' + node.id + '"]';
                } else {
                    let sibling = node.previousElementSibling;
                    let count = 1;
                    while (sibling) {
                        if (sibling.tagName === node.tagName) {
                            count++;
                        }
                        sibling = sibling.previousElementSibling;
                    }
                    if (count > 1) {
                        name += '[' + count + ']';
                    }
                }
                path.unshift(name);
                if (node === document.body) break;
            }
            return '/' + path.join('/');
        }

        // Helper: Get robust CSS Selector of element
        function getCSSSelector(element) {
            if (!element || element.nodeType !== Node.ELEMENT_NODE) return null;

            // Strategy 1: ID
            if (element.id && isSelectorUnique('#' + element.id, 'css')) {
                return '#' + element.id;
            }

            // Strategy 2: Name attribute (if unique)
            if (element.name && isSelectorUnique(element.tagName.toLowerCase() + '[name="' + element.name + '"]', 'css')) {
                return element.tagName.toLowerCase() + '[name="' + element.name + '"]';
            }

            // Strategy 3: Tag + classes (if unique)
            if (element.className && element.className.trim().length > 0) {
                const classes = element.className.split(/\\s+/).filter(c => c.length > 0);
                if (classes.length > 0) {
                    const classSelector = element.tagName.toLowerCase() + '.' + classes.join('.');
                    if (isSelectorUnique(classSelector, 'css')) {
                        return classSelector;
                    }
                }
            }

            // Fallback: nth-child (less stable)
            if (element.parentNode) {
                let selector = element.tagName.toLowerCase();
                let sibling = element.previousElementSibling;
                let count = 1;
                while (sibling) {
                    if (sibling.tagName === element.tagName) {
                        count++;
                    }
                    sibling = sibling.previousElementSibling;
                }
                if (count > 1) {
                    selector += ':nth-child(' + count + ')';
                }
                if (isSelectorUnique(selector, 'css')) {
                    return selector;
                }
            }

            // Fallback: Tag only
            return element.tagName.toLowerCase();
        }

        // Helper: Get all possible selectors for an element
        function getAllSelectors(element) {
            if (!element || element.nodeType !== Node.ELEMENT_NODE) return {};

            const selectors = {};

            // Basic attributes
            if (element.id) selectors.id = element.id;
            if (element.name) selectors.name = element.name;
            if (element.className) selectors.className = element.className;
            selectors.tagName = element.tagName.toLowerCase();
            if (element.innerText && element.innerText.trim().length > 0) selectors.text = element.innerText.trim().substring(0, 100);
            if (element.value) selectors.value = element.value;
            if (element.type) selectors.type = element.type;
            if (element.href) selectors.href = element.href;

            // XPath strategies
            selectors.xpath_id = element.id ? '//*[@id="' + element.id + '"]' : null;
            selectors.xpath_name = element.name ? '//' + selectors.tagName + '[@name="' + element.name + '"]' : null;
            selectors.xpath_text = selectors.text ? '//' + selectors.tagName + '[normalize-space(text())="' + selectors.text + '"]' : null;
            selectors.xpath_contains_text = selectors.text ? '//' + selectors.tagName + '[contains(normalize-space(text()),"' + selectors.text + '")]' : null;
            selectors.xpath_class = selectors.className ? '//' + selectors.tagName + '[' + selectors.className.split(/\\s+/).filter(c => c.length > 0).map(c => 'contains(@class,"' + c + '")').join(' and ') + ']' : null;
            selectors.xpath_indexed = getXPath(element);

            // CSS strategies
            selectors.css_id = element.id ? '#' + element.id : null;
            selectors.css_name = element.name ? selectors.tagName + '[name="' + selectors.name + '"]' : null;
            selectors.css_class = selectors.className ? selectors.tagName + '.' + selectors.className.split(/\\s+/).filter(c => c.length > 0).join('.') : null;
            selectors.css_nth_child = element.parentNode ? selectors.tagName + ':nth-child(' + (Array.from(element.parentNode.children).indexOf(element) + 1) + ')' : null;
            selectors.css_tag = selectors.tagName;

            // Filter and prioritize unique selectors
            const finalSelectors = {};
            const addedSelectors = new Set();

            const prioritizedSelectors = [
                { type: 'xpath', value: selectors.xpath_id },
                { type: 'css', value: selectors.css_id },
                { type: 'xpath', value: selectors.xpath_name },
                { type: 'css', value: selectors.css_name },
                { type: 'xpath', value: selectors.xpath_text },
                { type: 'xpath', value: selectors.xpath_contains_text },
                { type: 'xpath', value: selectors.xpath_class },
                { type: 'css', value: selectors.css_class },
                { type: 'css', value: selectors.css_nth_child },
                { type: 'xpath', value: selectors.xpath_indexed },
                { type: 'css', value: selectors.css_tag }
            ];

            for (const sel of prioritizedSelectors) {
                if (sel.value && !addedSelectors.has(sel.value)) {
                    if (isSelectorUnique(sel.value, sel.type)) {
                        finalSelectors[sel.type === 'xpath' ? 'xpath' : 'cssSelector'] = sel.value;
                        addedSelectors.add(sel.value);
                        if (sel.type === 'xpath' && finalSelectors.xpath) continue;
                        if (sel.type === 'css' && finalSelectors.cssSelector) continue;
                    }
                }
            }
            
            if (!finalSelectors.xpath && selectors.xpath_indexed) finalSelectors.xpath = selectors.xpath_indexed;
            if (!finalSelectors.cssSelector && selectors.css_tag) finalSelectors.cssSelector = selectors.css_tag;

            finalSelectors.allRawSelectors = selectors;

            return finalSelectors;
        }

        // Capture page hierarchy
        function captureHierarchy() {
            var elements = [];
            
            function traverse(node, depth) {
                if (depth > 10) return;
                
                if (node.nodeType === Node.ELEMENT_NODE) {
                    var rect = node.getBoundingClientRect();
                    const allSelectors = getAllSelectors(node);

                    elements.push({
                        tag: node.tagName.toLowerCase(),
                        id: node.id || null,
                        className: node.className || null,
                        text: node.innerText ? node.innerText.substring(0, 100) : null,
                        value: node.value || null,
                        name: node.name || null,
                        type: node.type || null,
                        href: node.href || null,
                        clickable: node.onclick != null || node.tagName === 'A' || node.tagName === 'BUTTON' || node.hasAttribute('role') && node.getAttribute('role') === 'button',
                        depth: depth,
                        bounds: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        },
                        xpath: allSelectors.xpath,
                        cssSelector: allSelectors.cssSelector,
                        allSelectors: allSelectors.allRawSelectors
                    });
                }
                
                for (var i = 0; i < node.children.length; i++) {
                    traverse(node.children[i], depth + 1);
                }
            }
            
            if (document.body) {
                traverse(document.body, 0);
            }
            
            return {
                url: window.location.href,
                title: document.title,
                totalElements: elements.length,
                elements: elements
            };
        }

        // Capture click events
        document.addEventListener('click', function(e) {
            var target = e.target;
            const allSelectors = getAllSelectors(target);
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
                xpath: allSelectors.xpath,
                xpathIndexed: allSelectors.allRawSelectors.xpath_indexed,
                cssSelector: allSelectors.cssSelector,
                allSelectors: allSelectors.allRawSelectors,
                innerHTML: target.outerHTML ? target.outerHTML.substring(0, 200) : null
            };
            
            try {
                window.webkit.messageHandlers.observeSDK.postMessage({
                    type: 'interaction',
                    data: data
                });
            } catch(e) {
                console.error('[MobiscoutSDK] Error sending click event:', e);
            }
        }, true);
        
        // Capture input events
        document.addEventListener('input', function(e) {
            var target = e.target;
            if (target.tagName.toLowerCase() === 'input' || 
                target.tagName.toLowerCase() === 'textarea') {
                const allSelectors = getAllSelectors(target);
                var data = {
                    eventType: 'input',
                    tag: target.tagName.toLowerCase(),
                    id: target.id || null,
                    className: target.className || null,
                    name: target.name || null,
                    type: target.type || null,
                    value: target.value ? '***' : null,
                    xpath: allSelectors.xpath,
                    xpathIndexed: allSelectors.allRawSelectors.xpath_indexed,
                    cssSelector: allSelectors.cssSelector,
                    allSelectors: allSelectors.allRawSelectors,
                    innerHTML: target.outerHTML ? target.outerHTML.substring(0, 200) : null
                };
                
                try {
                    window.webkit.messageHandlers.observeSDK.postMessage({
                        type: 'interaction',
                        data: data
                    });
                } catch(e) {
                    console.error('[MobiscoutSDK] Error sending input event:', e);
                }
            }
        }, true);
        
        // Capture form submit events
        document.addEventListener('submit', function(e) {
            var target = e.target;
            if (target.tagName.toLowerCase() === 'form') {
                const allSelectors = getAllSelectors(target);
                var data = {
                    eventType: 'submit',
                    tag: target.tagName.toLowerCase(),
                    id: target.id || null,
                    className: target.className || null,
                    name: target.name || null,
                    action: target.action || null,
                    method: target.method || null,
                    xpath: allSelectors.xpath,
                    xpathIndexed: allSelectors.allRawSelectors.xpath_indexed,
                    cssSelector: allSelectors.cssSelector,
                    allSelectors: allSelectors.allRawSelectors,
                    innerHTML: target.outerHTML ? target.outerHTML.substring(0, 200) : null
                };
                
                try {
                    window.webkit.messageHandlers.observeSDK.postMessage({
                        type: 'interaction',
                        data: data
                    });
                } catch(e) {
                    console.error('[MobiscoutSDK] Error sending submit event:', e);
                }
            }
        }, true);

        // Capture hierarchy on page load
        try {
            const hierarchy = captureHierarchy();
            window.webkit.messageHandlers.observeSDK.postMessage({
                type: 'pageLoad',
                url: window.location.href,
                hierarchy: JSON.stringify(hierarchy)
            });
        } catch(e) {
            console.error('[MobiscoutSDK] Error capturing initial hierarchy:', e);
        }
    })();
    """
}

