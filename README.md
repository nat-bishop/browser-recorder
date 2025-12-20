# browser-agents

Record browser interactions and convert them to AI agent tools.

## Quick Start

```bash
# Install dependencies
uv sync --extra dev

# Install Playwright browsers
uv run playwright install chromium

# Record a session
uv run browser-agents record https://example.com

# Replay a recording
uv run browser-agents replay recordings/<session-id>.jsonl

# Replay in headless mode
uv run browser-agents replay recordings/<session-id>.jsonl --headless

# Visual demo mode with cursor indicator and smooth movement
uv run browser-agents replay recordings/<session-id>.jsonl --demo

# Demo mode with custom timing
uv run browser-agents replay recordings/<session-id>.jsonl --demo --delay 0.5 --speed 30
```

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.
