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

```bash
# Launch Chrome with recorder extension
uv run browser-agents launch-chrome --url https://example.com

# In Chrome:
# 1. Press Shift+Alt+R to start recording
# 2. Perform your actions in the browser
# 3. Press Shift+Alt+R to stop recording
# 4. Save trace.zip from the recorder panel

# Import the trace
uv run browser-agents import-trace ~/Downloads/trace.zip
```

This captures user actions (clicks, typing, navigation) along with network requests.

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
  session.json              # RecordingSession (UIEvents + NetworkRequests)
  trace.zip                 # Original recording trace
  replay_trace.zip          # Playwright trace from replay (if --trace used)
  processed/
    workflow.json           # ActionDefinition from LLM conversion
```

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines.
