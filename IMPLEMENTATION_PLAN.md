# Implementation Plan

High-level roadmap for browser-agents. Each phase builds on the previous.

## Phase 1: Recording Foundation (MVP) ✅

**Goal:** Record browser interactions to JSONL files.

- [x] Project setup (pyproject.toml, CLAUDE.md)
- [x] Pydantic models for events (`RecordedEvent`, `Recording`)
- [x] CDP-based capture via Playwright
- [x] JSONL storage (append-only)
- [x] CLI (`uv run browser-agents record <url>`)

**Success:** Run recorder, click around a site, get valid JSONL output.

## Phase 2: Playback ✅

**Goal:** Replay recorded sessions reliably.

- [x] Load JSONL and validate with Pydantic
- [x] Execute actions via Playwright
- [x] Success/failure reporting
- [x] Screenshot on failure for debugging
- [x] CLI (`uv run browser-agents replay <file>`)

**Success:** Record a session, replay it, same result.

## Phase 3: Code Generation

**Goal:** Generate standalone Playwright scripts from recordings.

- [ ] Template-based code output
- [ ] Parameterized functions (not hardcoded values)
- [ ] Optional: AI-assisted selector improvement

**Success:** Generate a `.py` file that runs independently.

## Phase 4: Agent Integration

**Goal:** Use recordings as AI agent tools.

- [ ] LangChain tool wrapper for recordings
- [ ] Langfuse observability
- [ ] Provider abstraction (if swapping frameworks)

**Success:** An AI agent can invoke a recorded action as a tool.

## Phase 5: Advanced Capture

**Goal:** Richer context for better automation.

- [ ] Network traffic capture
- [ ] Voice/transcript integration
- [ ] Video frame analysis

**Success:** Capture API calls alongside clicks for context.

---

## Current Focus

**Testing & Validation** - Verify the recording/playback cycle works reliably before moving to Phase 3.

Next steps:
1. Test the workflow manually
2. Implement integration tests in `tests/test_browser.py`
3. Fix any issues found during testing
