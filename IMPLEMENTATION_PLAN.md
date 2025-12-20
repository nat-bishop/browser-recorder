# Implementation Plan

High-level roadmap for browser-agents. Each phase builds on the previous.

## Phase 1: Recording Foundation (MVP)

**Goal:** Record browser interactions to JSONL files.

- [x] Project setup (pyproject.toml, CLAUDE.md)
- [ ] Pydantic models for events (`RecordedEvent`, `Recording`)
- [ ] CDP-based capture via Playwright
- [ ] JSONL storage (append-only, crash-safe)
- [ ] CLI to start/stop recording (`uv run python -m browser_agents.recorder`)

**Success:** Run recorder, click around a site, get valid JSONL output.

## Phase 2: Playback

**Goal:** Replay recorded sessions reliably.

- [ ] Load JSONL and validate with Pydantic
- [ ] Execute actions via Playwright
- [ ] Success/failure reporting
- [ ] Screenshot on failure for debugging

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

**Phase 1** - Get recording working end-to-end.
