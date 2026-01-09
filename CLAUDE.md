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
│   ├── converter.py     # Session/Workflow → ActionDefinition via LLM
│   ├── demo.py          # Visual demo mode (cursor, smooth movement)
│   ├── llm.py           # LLM factory for Ollama/Anthropic/OpenAI
│   ├── models/          # NEW: Pydantic models package
│   │   ├── __init__.py  # Exports all models
│   │   ├── selectors.py # SelectorCandidate (6 strategies)
│   │   ├── events.py    # UIEvent, UIEventType (11 event types)
│   │   ├── session.py   # RecordingSession, SessionMetadata
│   │   └── workflow.py  # ActionDefinition, ActionStep
│   ├── models.py        # LEGACY: Old models (Workflow, RecordedEvent)
│   ├── playback/        # NEW: Session playback package
│   │   ├── __init__.py
│   │   ├── selector_resolver.py  # Codegen-style selector resolution
│   │   ├── executor.py  # SessionExecutor (11 event types)
│   │   └── safe_replay.py  # Network interception modes
│   ├── playback.py      # LEGACY: Workflow playback
│   ├── storage/         # NEW: Session storage package
│   │   ├── __init__.py
│   │   └── session_store.py  # SessionStore for sessions/
│   ├── recorder.py      # Event capture via injected JS
│   ├── js/              # NEW: Shared JavaScript
│   │   └── selector-generator.js  # Codegen-style selectors
│   └── prompts/
│       ├── convert_recording.yaml  # LLM prompt (legacy)
│       ├── convert_session.yaml    # LLM prompt (new session format)
│       └── diagnose_error.yaml     # LLM prompt for error diagnosis
├── browser-recorder-extension/  # NEW: Chrome Extension
│   ├── manifest.json    # MV3 config
│   ├── background.js    # Service worker
│   ├── content.js       # Event capture
│   ├── selector-generator.js  # Codegen-style selectors
│   ├── popup.html/js    # UI
│   └── icons/
├── tests/
│   ├── conftest.py      # Shared fixtures
│   ├── test_browser.py  # Integration tests - browser (slow)
│   ├── test_cli.py      # CLI tests - argument handling
│   ├── test_converter.py    # Converter tests (mocked LLM)
│   ├── test_models.py   # Unit tests - new models (UIEvent, SelectorCandidate)
│   ├── test_preprocessing.py  # Event preprocessing tests
│   └── test_selector_resolver.py  # Selector resolution tests
├── sessions/            # NEW: Chrome extension sessions
└── workflows/           # Playwright workflow storage
```

## CLI Usage

```bash
# === Chrome Extension Workflow (sessions/) ===

# Import session from Chrome extension export
uv run browser-agents import-session ~/Downloads/session.json

# List all sessions
uv run browser-agents list-sessions

# Replay session with multi-selector resolution
uv run browser-agents replay-session sessions/sess_abc123
uv run browser-agents replay-session sessions/sess_abc123 --safe --mode warn

# Convert session to ActionDefinition via LLM
uv run browser-agents convert-session sessions/sess_abc123 -d "Login and checkout"

# === Playwright Workflow (workflows/) ===

# Record browser interactions (saves to workflows/abc123/workflow.json)
uv run browser-agents record https://example.com
uv run browser-agents record https://example.com --output ./my-workflows

# Replay raw events from a workflow
uv run browser-agents replay workflows/abc123/workflow.json

# Visual demo mode (slow playback with cursor indicator)
uv run browser-agents replay workflows/abc123/workflow.json --demo

# Convert workflow to action definition (requires LLM)
uv run browser-agents convert workflows/abc123/workflow.json

# List all workflows
uv run browser-agents list

# Help
uv run browser-agents --help
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
| `test_models.py` | New model validation (UIEvent, SelectorCandidate) | Fast |
| `test_cli.py` | CLI argument handling | Fast |
| `test_converter.py` | Converter logic (mocked LLM) | Fast |
| `test_preprocessing.py` | Event preprocessing | Fast |
| `test_selector_resolver.py` | Selector resolution logic | Fast |
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

## Data Formats

### Sessions (Chrome Extension - `sessions/`)

**RecordingSession model:**
- Stored in `sessions/{id}/session.json`
- Contains: metadata + UIEvents with multi-selector candidates
- Converted output in `sessions/{id}/processed/workflow.json`

**UIEvent model:**
- 11 event types: `click`, `double_click`, `right_click`, `type`, `clear`, `select_option`, `check`, `uncheck`, `scroll`, `navigate`, `key_press`
- Multiple `SelectorCandidate` per event (Codegen-style)
- Selector priority: role > label > placeholder > text > testid > css

### Workflows (Playwright - `workflows/`)

**Unified Workflow model:**
- Single JSON file per session in `workflows/{id}/workflow.json`
- Contains: raw events + optional action definition + optional media refs
- Convert adds action in-place (same file)

**RecordedEvent model (legacy):**
- Event types: `click`, `type`, `navigate`, `scroll`, `wait`
- Single selector string per event

**Selector strategy:**
- Prefer data attributes (`[data-testid="..."]`)
- Fall back to stable CSS selectors
- Store coordinates as backup for resilience

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
