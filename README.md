# browser-agents

Record browser interactions and convert them to AI agent tools.

## Recording with Chrome Extension

Records from your existing browser session with all cookies, logins, and state:

```bash
# 1. Load the extension
#    Go to chrome://extensions > Load unpacked > select browser-recorder-extension/

# 2. Navigate to target page and click extension icon > "Start Recording"

# 3. Perform interactions, then click "Stop Recording" > "Export Session"

# 4. Import the exported session
uv run browser-agents import-session ~/Downloads/session.json
```

## Quick Start

```bash
# Install dependencies
uv sync --extra dev

# Install Playwright browsers
uv run playwright install chromium

# Import session from Chrome extension export
uv run browser-agents import-session ~/Downloads/session.json

# List all sessions
uv run browser-agents list-sessions

# Replay session with multi-selector resolution
uv run browser-agents replay-session sessions/sess_abc123
uv run browser-agents replay-session sessions/sess_abc123 --safe --mode warn

# Convert session to ActionDefinition via LLM
uv run browser-agents convert-session sessions/sess_abc123 -d "Login and checkout"
```

## Storage Format

```
sessions/{session_id}/
  session.json              # RecordingSession (UIEvents with multi-selector)
  processed/
    workflow.json           # ActionDefinition from LLM conversion
```

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.
