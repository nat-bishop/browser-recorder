# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- LLM-based recording conversion via `browser-agents convert` command
- ActionDefinition model for parameterized, reusable browser actions
- Event preprocessing to collapse verbose keystrokes and filter noise
- External YAML prompts for LLM instructions
- Structured output with automatic Pydantic validation
- Configuration via pydantic-settings with `.env` support

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
