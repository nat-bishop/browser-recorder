/**
 * Background service worker for Browser Recorder extension.
 *
 * Manages:
 * - Recording state per tab
 * - Event aggregation from all frames
 * - Session metadata
 * - Export functionality
 */

// Session state management
const sessions = new Map(); // tabId -> session data

/**
 * Generate a unique session ID.
 */
function generateSessionId() {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 8);
    return `sess_${timestamp}${random}`;
}

/**
 * Start recording for a tab.
 */
async function startRecording(tabId) {
    const tab = await chrome.tabs.get(tabId);

    const session = {
        metadata: {
            id: generateSessionId(),
            version: 1,
            started_at: new Date().toISOString(),
            ended_at: null,
            duration_ms: null,
            source_url: tab.url,
            browser_name: "Chrome",
            browser_version: navigator.userAgent.match(/Chrome\/(\d+\.\d+\.\d+\.\d+)/)?.[1] || "unknown",
            viewport_width: tab.width,
            viewport_height: tab.height
        },
        events: [],
        startTime: performance.now()
    };

    sessions.set(tabId, session);
    console.log("[Background] Session created for tab", tabId, session.metadata.id);

    // Notify content scripts to start recording
    try {
        const response = await chrome.tabs.sendMessage(tabId, {
            type: "startRecording",
            sessionStartTime: session.startTime
        });
        console.log("[Background] Content script response:", response);
    } catch (e) {
        // Content script may not be ready yet, that's ok
        console.log("[Background] Content script not ready:", e.message);
    }

    // Update badge
    await chrome.action.setBadgeText({ tabId, text: "REC" });
    await chrome.action.setBadgeBackgroundColor({ tabId, color: "#EF4444" });

    return session.metadata.id;
}

/**
 * Stop recording for a tab.
 */
async function stopRecording(tabId) {
    const session = sessions.get(tabId);
    if (!session) return null;

    session.metadata.ended_at = new Date().toISOString();
    session.metadata.duration_ms = Math.round(performance.now() - session.startTime);

    // Notify content scripts to stop recording
    try {
        await chrome.tabs.sendMessage(tabId, { type: "stopRecording" });
    } catch (e) {
        // Tab may have been closed
    }

    // Clear badge
    await chrome.action.setBadgeText({ tabId, text: "" });

    return session;
}

/**
 * Get current session for a tab.
 */
function getSession(tabId) {
    return sessions.get(tabId) || null;
}

/**
 * Check if currently recording.
 */
function isRecording(tabId) {
    const session = sessions.get(tabId);
    return session && !session.metadata.ended_at;
}

/**
 * Add an event to the current session.
 */
function addEvent(tabId, event) {
    const session = sessions.get(tabId);
    if (!session || session.metadata.ended_at) return false;

    session.events.push(event);
    return true;
}

/**
 * Export session as JSON (RecordingSession format).
 */
function exportSession(tabId) {
    const session = sessions.get(tabId);
    if (!session) return null;

    // Return clean RecordingSession format (without internal startTime)
    return {
        metadata: session.metadata,
        events: session.events
    };
}

/**
 * Clear session data for a tab.
 */
function clearSession(tabId) {
    sessions.delete(tabId);
}

// Message handling
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const tabId = sender.tab?.id || message.tabId;
    console.log("[Background] Message received:", message.type, "from tab:", tabId);

    switch (message.type) {
        case "startRecording":
            startRecording(tabId).then(sessionId => {
                sendResponse({ success: true, sessionId });
            });
            return true; // Will respond async

        case "stopRecording":
            stopRecording(tabId).then(session => {
                sendResponse({ success: true, eventCount: session?.events.length || 0 });
            });
            return true;

        case "getStatus":
            const session = getSession(tabId);
            sendResponse({
                isRecording: isRecording(tabId),
                eventCount: session?.events.length || 0,
                sessionId: session?.metadata.id || null
            });
            return false;

        case "recordEvent":
            const added = addEvent(tabId, message.event);
            sendResponse({ success: added });
            return false;

        case "exportSession":
            const exportData = exportSession(tabId);
            sendResponse({ success: !!exportData, data: exportData });
            return false;

        case "clearSession":
            clearSession(tabId);
            sendResponse({ success: true });
            return false;

        default:
            sendResponse({ error: "Unknown message type" });
            return false;
    }
});

// Track navigation for navigate events
if (chrome.webNavigation) {
    chrome.webNavigation.onCompleted.addListener((details) => {
        const tabId = details.tabId;
        const session = sessions.get(tabId);

        if (session && !session.metadata.ended_at && details.frameId === 0) {
            // Add navigate event for main frame navigation
            const event = {
                id: crypto.randomUUID(),
                event_type: "navigate",
                timestamp: new Date().toISOString(),
                relative_time_ms: Math.round(performance.now() - session.startTime),
                url: details.url,
                selectors: [],
                frame_type: "main"
            };
            session.events.push(event);
        }
    });
} else {
    console.warn("webNavigation API not available - navigate events will only be captured by content script");
}

// Clean up when tab is closed
chrome.tabs.onRemoved.addListener((tabId) => {
    sessions.delete(tabId);
});

// Handle extension icon click (start/stop recording)
chrome.action.onClicked.addListener(async (tab) => {
    if (isRecording(tab.id)) {
        await stopRecording(tab.id);
    } else {
        await startRecording(tab.id);
    }
});

console.log("Browser Recorder background script loaded");
