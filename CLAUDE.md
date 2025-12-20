# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

Browser-agents records user browser interactions and converts them to replayable automations (and eventually AI agent tools).

## Structure

```
browser-agents/
├── src/browser_agents/
│   ├── __init__.py      # Version and exports
│   ├── cli.py           # Combined CLI entry point
│   ├── models.py        # Pydantic models for recorded events
│   ├── recorder.py      # CDP-based capture
│   └── playback.py      # Replay recordings
├── tests/
│   ├── conftest.py      # Shared fixtures
│   ├── test_models.py   # Unit tests - Pydantic validation
│   └── test_cli.py      # CLI tests - argument handling
└── recordings/          # JSONL storage
```

## Environment Setup

Requires Python 3.11-3.13 (not 3.14 - future LangChain incompatibility).
Uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync --extra dev

# Install Playwright browsers (first time)
uv run playwright install chromium
```

## CLI Usage

```bash
# Record browser interactions
uv run browser-agents record https://example.com
uv run browser-agents record https://example.com --output ./my-recordings

# Replay a recording
uv run browser-agents replay recordings/abc123.jsonl
uv run browser-agents replay recordings/abc123.jsonl --headless

# Help
uv run browser-agents --help
uv run browser-agents record --help
```

## Testing

```bash
# Run all tests
uv run pytest

# Run only fast tests (skip browser tests)
uv run pytest -m "not slow"

# Run specific test file
uv run pytest tests/test_models.py -v

# Run with coverage
uv run pytest --cov=browser_agents
```

### Test Structure

| File | Purpose | Speed |
|------|---------|-------|
| `test_models.py` | Pydantic model validation | Fast |
| `test_cli.py` | CLI argument handling | Fast |
| `test_recording.py` | Full browser integration | Slow (marked `@pytest.mark.slow`) |

### Writing Tests

- **Unit tests**: Test models, parsing, pure functions
- **CLI tests**: Use `typer.testing.CliRunner` - no browser needed
- **Integration tests**: Mark with `@pytest.mark.slow` and `@pytest.mark.browser`
- **Fixtures**: Add shared fixtures to `conftest.py`

## Code Quality

Pre-commit hooks run automatically on `git commit`:
- `ruff` - Linting and formatting
- `mypy` - Type checking

```bash
# Manual runs
uv run ruff check src/ tests/ --fix
uv run mypy src/
```

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
- Brittle tests that test implementation details
