# browser-agents

Record browser interactions and convert them to AI agent tools.

## Recording Methods

Browser-agents supports two recording methods:

### 1. Chrome Extension (Recommended)

Records from your existing browser session with all cookies, logins, and state:

```bash
# 1. Load the extension
#    Go to chrome://extensions > Load unpacked > select browser-recorder-extension/

# 2. Navigate to target page and click extension icon > "Start Recording"

# 3. Perform interactions, then click "Stop Recording" > "Export Session"

# 4. Import the exported session
uv run browser-agents import-session ~/Downloads/session.json
```

### 2. Playwright Recorder

Launches a new browser instance for recording:

```bash
uv run browser-agents record https://example.com
uv run browser-agents record https://example.com --name "login-flow" --description "Login to example.com"
```

## Quick Start

```bash
# Install dependencies
uv sync --extra dev

# Install Playwright browsers
uv run playwright install chromium

# === Chrome Extension Workflow (sessions/) ===

# Import session from Chrome extension export
uv run browser-agents import-session ~/Downloads/session.json

# List all sessions
uv run browser-agents list-sessions

# Replay session with multi-selector resolution
uv run browser-agents replay-session sessions/sess_abc123
uv run browser-agents replay-session sessions/sess_abc123 --safe --mode warn

# Convert session to ActionDefinition via LLM
uv run browser-agents convert-session sessions/sess_abc123 -d "Login and checkout"

# === Playwright Workflow (workflows/) ===

# Record a session (saves to workflows/<session-id>/workflow.json)
uv run browser-agents record https://example.com

# Replay raw events from a workflow
uv run browser-agents replay workflows/<session-id>/workflow.json

# Visual demo mode with cursor indicator
uv run browser-agents replay workflows/<session-id>/workflow.json --demo

# Convert workflow to action definition
uv run browser-agents convert workflows/<session-id>/workflow.json -d "Description"

# List all workflows
uv run browser-agents list

# Replay action steps with parameters
uv run browser-agents replay workflows/<session-id>/workflow.json --action --param username=foo
```

## Storage Formats

### Sessions (Chrome Extension)

```
sessions/{session_id}/
  session.json              # RecordingSession (UIEvents with multi-selector)
  processed/
    workflow.json           # ActionDefinition from LLM conversion
```

### Workflows (Playwright)

```
workflows/{session_id}/
  workflow.json             # Unified Workflow (events + actions)
```

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.
