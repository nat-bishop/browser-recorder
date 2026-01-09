/**
 * Content script for Browser Recorder extension.
 *
 * Captures user interactions and sends them to the background script.
 * Uses selector-generator.js for generating Codegen-style selectors.
 *
 * Event types captured (matching UIEventType):
 * - click, double_click, right_click (mouse events)
 * - type, clear (input events)
 * - select_option (select changes)
 * - check, uncheck (checkbox/radio changes)
 * - scroll (debounced)
 * - key_press (special keys only)
 * - navigate (handled by background.js)
 */

// Prevent double initialization
if (window.__browserRecorderInitialized) {
    // Already initialized, just listen for messages
} else {
    window.__browserRecorderInitialized = true;

    // Recording state
    let isRecording = false;
    let sessionStartTime = 0;

    // Scroll debouncing
    let scrollTimeout = null;
    const SCROLL_DEBOUNCE_MS = 150;

    // Track last input value for detecting clears
    const lastInputValues = new WeakMap();

    /**
     * Check if we're in an iframe.
     */
    function isInIframe() {
        return window.self !== window.top;
    }

    /**
     * Get frame info.
     */
    function getFrameInfo() {
        if (isInIframe()) {
            return {
                frame_type: "iframe",
                frame_src: window.location.href
            };
        }
        return {
            frame_type: "main",
            frame_src: null
        };
    }

    /**
     * Send recorded event to background script.
     */
    function recordEvent(eventData) {
        if (!isRecording) {
            console.log("[Recorder] Event ignored - not recording:", eventData.event_type);
            return;
        }

        const frameInfo = getFrameInfo();
        const event = {
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            relative_time_ms: Math.round(performance.now() - sessionStartTime),
            url: window.location.href,
            ...eventData,
            ...frameInfo
        };

        console.log("[Recorder] Sending event:", event.event_type, event);
        chrome.runtime.sendMessage({
            type: "recordEvent",
            event: event
        }).then(response => {
            console.log("[Recorder] Event recorded:", response);
        }).catch((err) => {
            console.error("[Recorder] Failed to send event:", err);
        });
    }

    /**
     * Get common element metadata.
     */
    function getElementMeta(element) {
        const selectors = typeof generateSelectors === "function"
            ? generateSelectors(element)
            : [];

        const elementType = typeof getElementType === "function"
            ? getElementType(element)
            : "generic";

        const label = typeof findAssociatedLabel === "function"
            ? findAssociatedLabel(element)
            : null;

        return {
            selectors: selectors,
            element_type: elementType,
            element_label: label?.substring(0, 200) || null,
            element_text: element.innerText?.trim()?.substring(0, 200) || null,
            input_type: element.getAttribute("type") || null,
            placeholder: element.placeholder || null,
            x: null,
            y: null
        };
    }

    // =========================================================================
    // Event Listeners
    // =========================================================================

    /**
     * Handle click events.
     */
    function handleClick(e) {
        if (!isRecording) return;

        // Skip right-clicks - they're handled by handleContextMenu
        if (e.button === 2) return;

        const meta = getElementMeta(e.target);
        recordEvent({
            event_type: "click",
            ...meta,
            x: e.clientX,
            y: e.clientY
        });
    }

    /**
     * Handle double-click events.
     */
    function handleDoubleClick(e) {
        if (!isRecording) return;

        const meta = getElementMeta(e.target);
        recordEvent({
            event_type: "double_click",
            ...meta,
            x: e.clientX,
            y: e.clientY
        });
    }

    /**
     * Handle right-click (context menu) events.
     */
    function handleContextMenu(e) {
        if (!isRecording) return;

        const meta = getElementMeta(e.target);
        recordEvent({
            event_type: "right_click",
            ...meta,
            x: e.clientX,
            y: e.clientY
        });
    }

    /**
     * Handle input events (typing).
     */
    function handleInput(e) {
        if (!isRecording) return;

        const element = e.target;
        const tag = element.tagName.toLowerCase();

        // Only track text inputs
        if (tag !== "input" && tag !== "textarea") return;

        const inputType = element.getAttribute("type")?.toLowerCase();
        const textInputTypes = [
            "text", "email", "password", "tel", "url", "search", "number", null, ""
        ];

        if (tag === "input" && !textInputTypes.includes(inputType)) return;

        const currentValue = element.value;
        const lastValue = lastInputValues.get(element) || "";

        // Check if this is a clear operation
        if (currentValue === "" && lastValue !== "") {
            const meta = getElementMeta(element);
            recordEvent({
                event_type: "clear",
                ...meta
            });
        } else if (currentValue !== lastValue) {
            // Normal typing - record the full value
            const meta = getElementMeta(element);
            recordEvent({
                event_type: "type",
                ...meta,
                value: currentValue
            });
        }

        lastInputValues.set(element, currentValue);
    }

    /**
     * Handle change events (select, checkbox, radio).
     */
    function handleChange(e) {
        if (!isRecording) return;

        const element = e.target;
        const tag = element.tagName.toLowerCase();
        const inputType = element.getAttribute("type")?.toLowerCase();

        const meta = getElementMeta(element);

        if (tag === "select") {
            // Select option
            const selectedOption = element.options[element.selectedIndex];
            recordEvent({
                event_type: "select_option",
                ...meta,
                value: selectedOption?.text || element.value
            });
        } else if (inputType === "checkbox") {
            // Checkbox
            recordEvent({
                event_type: element.checked ? "check" : "uncheck",
                ...meta
            });
        } else if (inputType === "radio") {
            // Radio button
            recordEvent({
                event_type: "check",
                ...meta,
                value: element.value
            });
        }
    }

    /**
     * Handle scroll events (debounced).
     */
    function handleScroll(e) {
        if (!isRecording) return;

        // Clear previous timeout
        if (scrollTimeout) {
            clearTimeout(scrollTimeout);
        }

        // Debounce scroll events
        scrollTimeout = setTimeout(() => {
            const scrollX = window.scrollX || document.documentElement.scrollLeft;
            const scrollY = window.scrollY || document.documentElement.scrollTop;

            recordEvent({
                event_type: "scroll",
                selectors: [],
                scroll_x: Math.round(scrollX),
                scroll_y: Math.round(scrollY)
            });
        }, SCROLL_DEBOUNCE_MS);
    }

    /**
     * Handle keydown events (special keys only).
     */
    function handleKeyDown(e) {
        if (!isRecording) return;

        // Only capture special keys
        const specialKeys = [
            "Enter", "Tab", "Escape",
            "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
            "Backspace", "Delete",
            "Home", "End", "PageUp", "PageDown"
        ];

        if (!specialKeys.includes(e.key)) return;

        const meta = getElementMeta(e.target);
        recordEvent({
            event_type: "key_press",
            ...meta,
            key: e.key
        });
    }

    // =========================================================================
    // Setup event listeners
    // =========================================================================

    // Use capture phase to get events before they're handled
    document.addEventListener("click", handleClick, true);
    document.addEventListener("dblclick", handleDoubleClick, true);
    document.addEventListener("contextmenu", handleContextMenu, true);
    document.addEventListener("input", handleInput, true);
    document.addEventListener("change", handleChange, true);
    document.addEventListener("scroll", handleScroll, true);
    document.addEventListener("keydown", handleKeyDown, true);

    // =========================================================================
    // Message handling from background script
    // =========================================================================

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        console.log("[Recorder] Received message:", message.type, message);
        switch (message.type) {
            case "startRecording":
                isRecording = true;
                // Use content script's own performance.now() - don't use background's time
                // since they have different origins
                sessionStartTime = performance.now();
                lastInputValues.clear?.() || null; // Clear tracked values
                console.log("[Recorder] Recording STARTED, sessionStartTime:", sessionStartTime);
                sendResponse({ success: true });
                break;

            case "stopRecording":
                isRecording = false;
                console.log("[Recorder] Recording STOPPED");
                sendResponse({ success: true });
                break;

            case "getStatus":
                sendResponse({ isRecording });
                break;

            default:
                sendResponse({ error: "Unknown message type" });
        }
        return false;
    });

    // Check initial recording state
    chrome.runtime.sendMessage({ type: "getStatus" }, (response) => {
        if (response?.isRecording) {
            isRecording = true;
            // Note: sessionStartTime won't be perfectly accurate for late-loaded iframes
            sessionStartTime = performance.now();
        }
    });

    console.log("Browser Recorder content script loaded", isInIframe() ? "(iframe)" : "(main)");
}
