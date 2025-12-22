# Implementation Plan

High-level roadmap for browser-agents. Each phase builds on the previous.

## Research Summary (Dec 2024)

**Key finding:** This project is NOT duplicating existing tools. The use case (constrained, pre-recorded workflows as agent tools) is different from:

- [Browser-Use](https://github.com/browser-use/browser-use) - gives AI free reign over browser
- [Skyvern](https://github.com/Skyvern-AI/skyvern) - dynamic AI control, not recorded workflows
- [Playwright Codegen](https://playwright.dev/docs/codegen) - generates test code, not replayable actions

**What we borrow:**
- Browser-Use's decorator pattern for tool registration
- Skyvern's Vision LLM approach (Phase 6, future)

## Phase 1: Recording Foundation (MVP) ✅

**Goal:** Record browser interactions to JSONL files.

- [x] Project setup (pyproject.toml, CLAUDE.md)
- [x] Pydantic models for events (`RecordedEvent`, `Recording`)
- [x] Event capture via injected JavaScript listeners
- [x] JSONL storage (append-only)
- [x] CLI (`uv run browser-agents record <url>`)

**Implementation notes:**
- Uses `page.expose_function()` + `page.add_init_script()` to inject event listeners
- Captures click, input, scroll, and navigation events
- Selector generation prioritizes: data-testid > id > aria-label > name > tag+classes

**Success:** Run recorder, click around a site, get valid JSONL output.

## Phase 2: Playback ✅

**Goal:** Replay recorded sessions reliably.

- [x] Load JSONL and validate with Pydantic
- [x] Execute actions via Playwright
- [x] Success/failure reporting
- [x] Screenshot on failure for debugging
- [x] CLI (`uv run browser-agents replay <file>`)

**Success:** Record a session, replay it, same result.

## Phase 3: Recording → Action Conversion

**Goal:** Convert raw recordings into clean, parameterized action definitions using LLM.

Raw recordings are messy (hundreds of low-level events). Use LLM summarization to extract:
- Action name and description
- Variable parameters (e.g., email, address, product ID)
- Simplified step sequence with `{parameter}` placeholders

- [x] Define `ActionDefinition` Pydantic model
- [x] Create LLM prompt for recording → action conversion
- [x] Implement `convert_recording_to_action()` function
- [x] CLI: `uv run browser-agents convert recordings/foo.jsonl`
- [x] Store converted actions in `actions/` directory

**Success:** `browser-agents convert recording.jsonl` outputs a clean action JSON.

### Implementation Notes (Dec 2025)

- Uses `ChatOpenAI` with Ollama `/v1` endpoint (pattern from ai-agents)
- Model: `gpt-oss:120b` (configurable via `LOCAL_MODEL` env var)
- Event preprocessing: Collapses keystrokes, removes scroll noise, deduplicates navigations
- Prompt includes few-shot example for consistency
- Error handling: Retry with exponential backoff, post-call validation

## Phase 4: Agent Integration

**Goal:** Use action definitions as constrained AI agent tools.

### Browser-Use Pattern (Recommended)

Adopt decorator-based tool registration inspired by [Browser-Use](https://github.com/browser-use/browser-use):

```python
from browser_agents import tools

@tools.action("checkout.json")
async def checkout(shipping_address: str) -> ActionResult:
    """Complete checkout with the given address."""
    pass  # Playback happens automatically
```

### Tasks

- [ ] Decorator-based tool interface (`@tools.action()`)
- [ ] Parameter substitution in action playback
- [ ] `ActionResult` return type for agent decision-making
- [ ] Domain restrictions for safety (`allowed_domains=['example.com']`)
- [ ] LangChain compatibility
- [ ] Langfuse observability

**Success:** An AI agent can invoke an action as a constrained tool.

## Phase 5: Advanced Capture

**Goal:** Richer context for better automation.

- [ ] Network traffic capture
- [ ] Voice/transcript integration
- [ ] Video frame analysis

**Success:** Capture API calls alongside clicks for context.

## Phase 6: Vision LLM UI Resilience (Future)

**Goal:** Make actions resilient to UI changes using Vision LLMs.

**NOT part of MVP** - This is future work after core functionality is stable.

### How Skyvern Does It

[Skyvern](https://github.com/Skyvern-AI/skyvern) uses Vision LLMs instead of selectors:
- Processes screenshots to understand page visually
- Identifies elements by appearance, not XPath/CSS
- Self-heals when UI layouts change
- Recognizes equivalent elements ("Submit" vs "Send Message")

### Approach for browser-agents

- [ ] Store screenshots with each recorded event
- [ ] On playback failure, send screenshot to Vision LLM
- [ ] Vision LLM locates equivalent element visually
- [ ] Fall back to visual matching when CSS selectors break
- [ ] Consider: Claude Vision, GPT-4o, or open models

**Success:** Recorded workflow survives a UI redesign without manual updates.

---

## Current Focus

**Phase 3 Complete** - Recording → Action conversion with LLM analysis is working.

### Phase 3: Convert Command

Convert raw recordings to parameterized action definitions:
```bash
uv run browser-agents convert recordings/abc123.jsonl
```

Features:
- Event preprocessing (collapses keystrokes, removes scroll noise)
- LLM-based analysis using `gpt-oss:120b` via Ollama
- Structured output with Pydantic validation
- Automatic parameter extraction (usernames, passwords, etc.)
- Retry logic with exponential backoff

### Test Coverage (44 tests, all passing)
- Unit tests: Models, CLI, preprocessing, converter (mocked LLM)
- Integration tests: Playback, recording capture, full roundtrip
- Slow tests: Real LLM conversion (skipped by default)

### Next Steps
1. Phase 4: Agent Integration (decorator-based tool interface)
2. Consider adding more event types (hover, select, etc.) as needed
