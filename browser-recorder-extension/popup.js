/**
 * Popup UI logic for Browser Recorder extension.
 */

// DOM elements
const indicator = document.getElementById("indicator");
const statusText = document.getElementById("status-text");
const eventCount = document.getElementById("event-count");
const sessionIdEl = document.getElementById("session-id");
const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const exportBtn = document.getElementById("export-btn");
const clearBtn = document.getElementById("clear-btn");

// Current tab ID
let currentTabId = null;

/**
 * Get current tab.
 */
async function getCurrentTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
}

/**
 * Update UI based on recording state.
 */
function updateUI(isRecording, events, sessionId) {
    // Update indicator
    indicator.classList.toggle("active", isRecording);

    // Update status text
    statusText.textContent = isRecording ? "Recording" : "Stopped";

    // Update event count
    eventCount.textContent = events.toString();

    // Update session ID
    sessionIdEl.textContent = sessionId || "";

    // Update buttons
    startBtn.classList.toggle("hidden", isRecording);
    stopBtn.classList.toggle("hidden", !isRecording);
    exportBtn.disabled = events === 0;
    clearBtn.disabled = events === 0 && !isRecording;
}

/**
 * Refresh status from background script.
 */
async function refreshStatus() {
    if (!currentTabId) return;

    try {
        const response = await chrome.runtime.sendMessage({
            type: "getStatus",
            tabId: currentTabId
        });

        updateUI(
            response.isRecording || false,
            response.eventCount || 0,
            response.sessionId || null
        );
    } catch (e) {
        console.error("Failed to get status:", e);
    }
}

/**
 * Start recording.
 */
async function startRecording() {
    if (!currentTabId) return;

    try {
        const response = await chrome.runtime.sendMessage({
            type: "startRecording",
            tabId: currentTabId
        });

        if (response.success) {
            updateUI(true, 0, response.sessionId);
        }
    } catch (e) {
        console.error("Failed to start recording:", e);
    }
}

/**
 * Stop recording.
 */
async function stopRecording() {
    if (!currentTabId) return;

    try {
        const response = await chrome.runtime.sendMessage({
            type: "stopRecording",
            tabId: currentTabId
        });

        if (response.success) {
            updateUI(false, response.eventCount, null);
        }
    } catch (e) {
        console.error("Failed to stop recording:", e);
    }
}

/**
 * Export session as JSON file.
 */
async function exportSession() {
    if (!currentTabId) return;

    try {
        const response = await chrome.runtime.sendMessage({
            type: "exportSession",
            tabId: currentTabId
        });

        if (response.success && response.data) {
            const json = JSON.stringify(response.data, null, 2);
            const blob = new Blob([json], { type: "application/json" });
            const url = URL.createObjectURL(blob);

            // Create download link
            const a = document.createElement("a");
            a.href = url;
            a.download = `${response.data.metadata.id}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }
    } catch (e) {
        console.error("Failed to export session:", e);
    }
}

/**
 * Clear current session.
 */
async function clearSession() {
    if (!currentTabId) return;

    try {
        await chrome.runtime.sendMessage({
            type: "clearSession",
            tabId: currentTabId
        });

        updateUI(false, 0, null);
    } catch (e) {
        console.error("Failed to clear session:", e);
    }
}

// Event listeners
startBtn.addEventListener("click", startRecording);
stopBtn.addEventListener("click", stopRecording);
exportBtn.addEventListener("click", exportSession);
clearBtn.addEventListener("click", clearSession);

// Initialize
(async () => {
    const tab = await getCurrentTab();
    currentTabId = tab?.id;

    if (currentTabId) {
        await refreshStatus();

        // Poll for updates while popup is open
        setInterval(refreshStatus, 1000);
    }
})();
