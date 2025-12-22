# browser-agents

Record browser interactions and convert them to AI agent tools.

## Quick Start

```bash
# Install dependencies
uv sync --extra dev

# Install Playwright browsers
uv run playwright install chromium

# Record a session (saves to workflows/<session-id>.json)
uv run browser-agents record https://example.com

# Replay raw events from a workflow
uv run browser-agents replay workflows/<session-id>.json

# Visual demo mode with cursor indicator and smooth movement
uv run browser-agents replay workflows/<session-id>.json --demo

# Demo mode with custom timing
uv run browser-agents replay workflows/<session-id>.json --demo --delay 0.5 --speed 30

# Convert workflow events to action definition (requires Ollama)
uv run browser-agents convert workflows/<session-id>.json

# Replay action steps with parameter substitution
uv run browser-agents replay workflows/<session-id>.json --action
uv run browser-agents replay workflows/<session-id>.json --action --param username=foo --param password=bar
```

## Workflow Format

Browser-agents uses a unified `Workflow` JSON format stored in `workflows/`:

- **Raw events**: Captured browser interactions (clicks, typing, navigation)
- **Action definition**: LLM-derived parameterized steps (added by `convert`)
- **Media refs**: Optional video/audio references (future)

This single-file format enables provenance tracking (raw events are preserved alongside derived actions).

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.
