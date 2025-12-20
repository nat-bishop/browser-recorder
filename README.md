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
```

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.
