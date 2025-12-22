# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Browser-agents records user browser interactions and converts them to replayable automations (and eventually AI agent tools).

## Structure

```
browser-agents/
├── src/browser_agents/
│   ├── __init__.py      # Version and exports
│   ├── cli.py           # Combined CLI entry point
│   ├── config.py        # Settings via pydantic-settings (.env support)
│   ├── converter.py     # Recording → ActionDefinition via LLM
│   ├── demo.py          # Visual demo mode (cursor, smooth movement)
│   ├── llm.py           # LLM factory for Ollama
│   ├── models.py        # Pydantic models for events and actions
│   ├── playback.py      # Replay recordings
│   ├── recorder.py      # Event capture via injected JS
│   └── prompts/
│       └── convert_recording.yaml  # LLM prompt for conversion
├── tests/
│   ├── conftest.py      # Shared fixtures
│   ├── test_browser.py  # Integration tests - browser (slow)
│   ├── test_cli.py      # CLI tests - argument handling
│   ├── test_converter.py    # Converter tests (mocked LLM)
│   ├── test_models.py   # Unit tests - Pydantic validation
│   └── test_preprocessing.py  # Event preprocessing tests
└── recordings/          # JSONL storage
```

## CLI Usage

```bash
# Record browser interactions
uv run browser-agents record https://example.com
uv run browser-agents record https://example.com --output ./my-recordings

# Replay a recording
uv run browser-agents replay recordings/abc123.jsonl
uv run browser-agents replay recordings/abc123.jsonl --headless

# Visual demo mode (slow playback with cursor indicator)
uv run browser-agents replay recordings/abc123.jsonl --demo
uv run browser-agents replay recordings/abc123.jsonl --demo --delay 0.5 --speed 30

# Convert recording to action definition (requires Ollama)
uv run browser-agents convert recordings/abc123.jsonl
uv run browser-agents convert recordings/abc123.jsonl -o ./actions

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
| `test_converter.py` | Converter logic (mocked LLM) | Fast |
| `test_preprocessing.py` | Event preprocessing | Fast |
| `test_browser.py` | Full browser integration | Slow (marked `@pytest.mark.slow`) |

### Test Markers

- `@pytest.mark.slow` - Tests that take >1s (browser tests)
- `@pytest.mark.browser` - Tests requiring Playwright browsers

Use `pytest -m "not slow"` for fast CI runs.

### Writing Tests

- **Unit tests**: Test models, parsing, pure functions
- **CLI tests**: Use `typer.testing.CliRunner` - no browser needed
- **LLM tests**: Mock `get_structured_llm` to avoid API calls (see `test_converter.py`)
- **Integration tests**: Mark with `@pytest.mark.slow` and `@pytest.mark.browser`
- **Fixtures**: Add shared fixtures to `conftest.py`

## Code Quality

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
