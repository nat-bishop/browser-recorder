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

### Option 1: Record via CDP (recommended)

```bash
# Launch Chrome with debugging port
uv run browser-agents launch-chrome --url https://example.com

# Start recording (keeps connection alive)
uv run browser-agents record

# Perform actions in the browser, then press Enter to stop
# Session is auto-imported with trace.zip and network requests
```

### Option 2: Import existing trace.zip

```bash
uv run browser-agents import-trace ~/Downloads/trace.zip
```

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
