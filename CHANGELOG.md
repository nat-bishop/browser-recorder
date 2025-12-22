# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Workflow Model v2** with enhanced metadata
  - `name` and `description` fields for human-readable workflow identification
  - `version` field (currently 2) for schema migrations
  - `actions` list supporting multiple action definitions per workflow (was singular `action`)
  - Legacy `action` field auto-converts to `actions` list on load
- **New CLI commands and options**
  - `record --name/-n` and `--description/-d` flags for workflow metadata
  - `replay --name/-n` flag to select which action to replay (for multi-action workflows)
  - New `list` command to display all workflows with their names and actions
  - `convert` now appends to actions list (can run multiple times for different interpretations)
- **Recording improvements**
  - Browser close detection - recording stops when user closes browser window (via page "close" event)
  - Ctrl+C still works as alternative stop method
- **Guided replay improvements**
  - New "describe fix" option `[f]` - user describes problem in natural language
  - `StepFixSuggestion` model for LLM-generated fix suggestions
  - LLM interprets feedback and suggests: delete, modify, or keep
  - New `select` action type for `<select>` dropdown elements
  - New "go back" option `[b]` - rewind to fix an earlier step that caused a failure
  - Look-ahead warning system: detects when next step's target element is missing
  - `StepHistory` tracking with status indicators (OK, WARN, FAIL) for step visualization
  - Look-ahead warnings display as "[Next step issue]" in step history
  - Go-back menu shows the actual step predicted to fail, not the detecting step
  - Rewind waits for page load and adds pauses between steps for reliability
  - Abort handling shows partial run notice and defaults to NOT saving changes
- Guided replay mode (`--guided` / `-g` flag) with interactive error handling
- LLM-based error diagnosis for guided replay using `diagnose_error.yaml` prompt
  - Classifies errors as: `conversion` (wrong step), `execution` (step failed), `verification` (wrong result)
  - Provides plain-language explanation, likely cause, and suggestions
  - Falls back to pattern matching when Ollama is unavailable
- `ErrorDiagnosis` model for structured LLM diagnosis output
- `SuccessCondition` model for defining workflow success criteria
- `set-success` command to configure success conditions for workflows
- Re-record functionality during guided replay to fix incorrect steps
- Session folder structure for recordings (`workflows/{session_id}/workflow.json`)
- Screenshot support in `RecordedEvent` and `ActionStep` models
- LLM-based recording conversion via `browser-agents convert` command
- ActionDefinition model for parameterized, reusable browser actions
- Event preprocessing to collapse verbose keystrokes and filter noise
- External YAML prompts for LLM instructions
- Structured output with automatic Pydantic validation
- Configuration via pydantic-settings with `.env` support

### Changed

- Workflow schema updated from v1 to v2 (backward compatible)

## [0.1.0] - 2025-12-20

Initial release with recording and playback capabilities.

### Added

- **Recording**: Capture browser interactions via injected JavaScript
  - Click events with CSS selector and coordinate fallback
  - Text input events with selector-based targeting
  - Scroll position tracking
  - Navigation events via Playwright frame detection
  - JSONL storage format (metadata + events)
- **Playback**: Replay recorded sessions
  - Selector-based element targeting with coordinate fallback
  - All event types: navigate, click, type, scroll, wait
- **Demo Mode**: Visual playback for review
  - SVG cursor indicator with click animation
  - Smooth mouse movement interpolation
  - Configurable delay with random jitter
- **CLI**: Unified command interface
  - `browser-agents record <url>` - Start recording
  - `browser-agents replay <file>` - Replay a session
  - `--demo`, `--delay`, `--speed` options
- **Models**: Pydantic data structures
  - RecordedEvent for individual browser events
  - Recording for complete sessions with metadata
- **Testing**: pytest framework with async support
  - Fast unit tests for models and CLI
  - Browser integration tests marked `@pytest.mark.slow`
