# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

Browser-agents records user browser interactions and converts them to replayable automations (and eventually AI agent tools).

## Structure

```
src/browser_agents/
├── __init__.py      # Version and exports
├── models.py        # Pydantic models for recorded events
├── recorder.py      # CDP-based capture + CLI
└── playback.py      # Replay recordings
```

## Environment Setup

Requires Python 3.11-3.13 (not 3.14 - future LangChain incompatibility).
Uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync --extra dev

# Install Playwright browsers (first time)
uv run playwright install chromium

# Run any command
uv run python -m browser_agents.recorder record https://example.com
```

## Commands

```bash
uv sync --extra dev                    # Install/update all deps
uv run python -m browser_agents.recorder record <url>  # Start recording
uv run python -m browser_agents.playback <file>        # Replay recording
```

## Code Quality

Pre-commit hooks run automatically on `git commit`:
- `ruff` - Linting and formatting
- `mypy` - Type checking

## Principles

**Keep it simple:**
- Don't abstract until there's duplication (Rule of Three)
- YAGNI - don't build what we don't need yet

**Async execution:**
- Playwright is async - use `async def` for all browser operations
- Runner pattern: `asyncio.run(main())`

**Error handling:**
- Return error strings for recoverable failures (not exceptions)
- Let unexpected errors propagate

## Recording Conventions

**Event model:**
- All events are Pydantic `RecordedEvent` models
- Storage: JSONL (one event per line, append-only)
- Validation: At boundary when reading files

**Selector strategy:**
- Prefer data attributes (`[data-testid="..."]`)
- Fall back to stable CSS selectors
- Store coordinates as backup

**Event types:**
- `click` - element clicked
- `type` - text entered
- `navigate` - page URL changed
- `scroll` - viewport scrolled
- `wait` - explicit pause

## Windows Console Encoding

When printing output to Windows console, handle unicode:

```python
content = text.encode('ascii', 'replace').decode('ascii')
print(content)
```

## Anti-Patterns to Avoid

- Config for features that don't exist yet
- Abstracting before there's duplication
- Documenting aspirational features as if they exist
- Hardcoding values that should be in models
