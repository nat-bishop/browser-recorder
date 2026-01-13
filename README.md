# browser-agents

Record browser interactions and convert them to AI agent tools.

## Quick Start

```bash
# Install dependencies
uv sync --extra dev

# Install Playwright browsers
uv run playwright install chromium
```

## Recording

### Option 1: Use the built-in recorder (recommended)

```bash
# Build the recorder extension (first time only)
cd recorder && npm install && npm run build && cd ..

# Load in Chrome:
# 1. Go to chrome://extensions
# 2. Enable "Developer mode"
# 3. Click "Load unpacked" and select recorder/extension/dist/

# Record your session, then export trace.zip and import:
uv run browser-agents import-trace ~/Downloads/trace.zip
```

### Option 2: Use Chrome DevTools Recorder

No build required - use Chrome's built-in recorder:

1. Open Chrome DevTools (F12)
2. Go to "Recorder" panel
3. Record your actions
4. Export as JSON
5. Import with: `uv run browser-agents import-session recording.json`

## Replay

```bash
# List sessions
uv run browser-agents list-sessions

# Replay a session
uv run browser-agents replay-session sessions/sess_abc123

# Replay with safe mode (blocks POST/PUT/DELETE requests)
uv run browser-agents replay-session sessions/sess_abc123 --safe

# Replay with tracing (saves trace.zip for debugging)
uv run browser-agents replay-session sessions/sess_abc123 --trace

# View the trace
npx playwright show-trace sessions/sess_abc123/replay_trace.zip
```

## Convert to AI Agent Tool

```bash
# Convert session to ActionDefinition via LLM
uv run browser-agents convert-session sessions/sess_abc123 -d "Login and checkout"
```

## Storage Format

```
sessions/{session_id}/
  session.json              # RecordingSession (UIEvents with multi-selector)
  replay_trace.zip          # Playwright trace from replay (if --trace used)
  processed/
    workflow.json           # ActionDefinition from LLM conversion
```

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines.
