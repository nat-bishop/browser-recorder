# Production Browser Automation System - Implementation Progress

## Overview

Building a production-grade browser recording system with:
- Chrome Extension for universal capture (including iframes)
- Codegen-style selectors (role, label, placeholder, text, testid, css)
- Video + audio recording (synchronized with events)
- Session-based storage with LLM-derived workflows

**Explicitly NOT included (by design):**
- Network traffic capture (security concerns, marginal LLM value)
- Screenshots (video covers this)

## Progress Summary

| Sprint | Status | Description |
|--------|--------|-------------|
| Sprint 1 | ✅ Complete | Core Models & Selector Generator |
| Sprint 2 | ✅ Complete | Multi-Selector Playback |
| Sprint 3 | ⏳ Pending | Chrome Extension MVP |
| Sprint 4 | ⏳ Pending | Polish, Conversion & Video |

---

## Sprint 1: Core Models & Selector Generator ✅

**Status**: Complete
**Completed**: 2025-01-09

### Deliverables

| Task | Status | Files |
|------|--------|-------|
| Create models/ package | ✅ | `src/browser_agents/models/` |
| SelectorCandidate model | ✅ | `models/selectors.py` |
| UIEvent, UIEventType models | ✅ | `models/events.py` |
| RecordingSession, SessionMetadata | ✅ | `models/session.py` |
| ActionDefinition, workflow models | ✅ | `models/workflow.py` |
| Selector generator JS | ✅ | `src/browser_agents/js/selector-generator.js` |
| Rewrite recorder.py | ✅ | `src/browser_agents/recorder.py` |
| Create storage/ package | ✅ | `src/browser_agents/storage/` |
| SessionStore class | ✅ | `storage/session_store.py` |
| Rewrite test_models.py | ✅ | `tests/test_models.py` |

### New File Structure Created

```
src/browser_agents/
├── models/                        ✅ NEW
│   ├── __init__.py               # Exports all models
│   ├── selectors.py              # SelectorCandidate
│   ├── events.py                 # UIEvent, UIEventType (11 event types)
│   ├── session.py                # RecordingSession, SessionMetadata, VideoInfo
│   └── workflow.py               # ActionDefinition, ActionStep, error models
├── storage/                       ✅ NEW
│   ├── __init__.py
│   └── session_store.py          # SessionStore for load/save
├── js/                            ✅ NEW
│   └── selector-generator.js     # 400+ lines Codegen-style selectors
├── recorder.py                    ✅ REWRITTEN (uses new models)
└── __init__.py                    ✅ UPDATED (exports new models)
```

### Test Results

```
tests/test_models.py: 42 passed in 0.06s
```

### Key Features Implemented

**SelectorCandidate** - 6 strategies with confidence levels:
| Strategy | Confidence | Example |
|----------|------------|---------|
| `role` | high | `role=button[name="Submit"]` |
| `label` | high | `Email` (form label) |
| `placeholder` | medium | `Enter your email` |
| `text` | medium | `Sign In` (button text) |
| `testid` | high | `submit-btn` |
| `css` | low | `#submit-button` |

**UIEventType** - 11 event types:
- `click`, `double_click`, `right_click`
- `type`, `clear`, `select_option`
- `check`, `uncheck`
- `scroll`, `navigate`, `key_press`

**Selector Generator JS** (400+ lines):
- Implicit ARIA role detection (button, textbox, link, etc.)
- Accessible name computation (aria-label, labelledby, text content)
- Smart CSS generation (avoids brittle auto-generated IDs)
- Test ID detection (data-testid, data-test-id, data-cy)

---

## Sprint 2: Multi-Selector Playback ✅

**Status**: Complete
**Completed**: 2025-01-09

### Deliverables

| Task | Status | Files |
|------|--------|-------|
| Create playback/ package | ✅ | `src/browser_agents/playback/` |
| SelectorResolver class | ✅ | `playback/selector_resolver.py` |
| Session executor | ✅ | `playback/executor.py` |
| Safe replay mode | ✅ | `playback/safe_replay.py` |
| Update CLI replay command | ✅ | `src/browser_agents/cli.py` |
| Selector resolution tests | ✅ | `tests/test_selector_resolver.py` |

### New File Structure Created

```
src/browser_agents/
├── playback/                      ✅ NEW
│   ├── __init__.py               # Exports all playback classes
│   ├── selector_resolver.py      # Codegen-style resolution (147 lines)
│   ├── executor.py               # Session replay (235 lines)
│   └── safe_replay.py            # Method-based network blocking (126 lines)
```

### New CLI Commands

```bash
# Replay session with new format
uv run browser-agents replay-session sessions/sess_abc123
uv run browser-agents replay-session sessions/sess_abc123 --safe
uv run browser-agents replay-session sessions/sess_abc123 --safe --mode warn

# Import session from extension export
uv run browser-agents import-session ~/Downloads/workflow.json

# List all sessions
uv run browser-agents list-sessions
```

### Key Features Implemented

**SelectorResolver** - Priority-based resolution:
```python
# Priority: role → label → placeholder → text → testid → css
async def resolve(self, event: UIEvent) -> Locator | None:
    for candidate in event.selectors:
        locator = self._to_locator(candidate)
        if await locator.count() == 1:
            return locator
    return None  # Fall back to coordinates
```

**SessionExecutor** - Handles all 11 event types with coordinate fallback

**Safe Replay Mode** - Block state-changing requests:
| Mode | Behavior |
|------|----------|
| `LIVE` | No interception |
| `WARN` | Log but allow POST/PUT/DELETE |
| `BLOCK` | Abort state-changing requests |
| `MOCK` | Return fake success responses |

---

## Sprint 3: Chrome Extension MVP ⏳

**Status**: Pending
**Target**: Week 2-3

### Tasks

| Task | Status | Files |
|------|--------|-------|
| Extension manifest | ⏳ | `browser-recorder-extension/manifest.json` |
| Background script | ⏳ | `browser-recorder-extension/background.js` |
| Content script | ⏳ | `browser-recorder-extension/content.js` |
| Popup UI | ⏳ | `browser-recorder-extension/popup.html` |
| CLI import command | ⏳ | `src/browser_agents/cli.py` |

### Target File Structure

```
browser-recorder-extension/        ⏳ NEW
├── manifest.json                 # MV3, all_frames: true
├── background.js                 # Service worker, session state
├── content.js                    # Event capture (reuses selector-generator.js)
├── popup.html                    # Start/stop UI
├── popup.js                      # UI logic
└── icons/
```

### Key Advantage Over Playwright
- `all_frames: true` enables iframe capture
- User's existing Chrome session (logged in, cookies)
- No browser launch overhead

---

## Sprint 4: Polish, Conversion & Video ⏳

**Status**: Pending
**Target**: Week 3-4

### Tasks

| Task | Status | Files |
|------|--------|-------|
| Update LLM conversion | ⏳ | `src/browser_agents/converter.py` |
| Video capture | ⏳ | `browser-recorder-extension/video-capture.js` |
| Update conversion prompt | ⏳ | `src/browser_agents/prompts/convert_session.yaml` |
| Error handling | ⏳ | Various |
| Documentation | ⏳ | `README.md` |

### Key Features
- LLM converts UIEvents → ActionDefinition
- Video via chrome.tabCapture API
- Timestamp sync via `relative_time_ms`

---

## Storage Structure

```
sessions/                          # NEW storage location
└── {session_id}/
    ├── session.json              # RecordingSession (metadata + events)
    ├── media/
    │   └── recording.webm        # Video (optional, Sprint 4)
    └── processed/
        └── workflow.json         # LLM-derived ActionDefinition
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CAPTURE LAYER                                        │
│  Chrome Extension (primary) OR Playwright (dev/testing)                      │
│  Produces: UIEvent with Codegen-style selectors                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SESSION STORAGE                                         │
│  sessions/{id}/session.json + media/recording.webm (optional)               │
│  Raw events stored, LLM processing generates workflow.json                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PROCESSED OUTPUT                                        │
│  sessions/{id}/processed/workflow.json (ActionDefinition)                   │
│  Generated by LLM from raw events, can be re-generated                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Testing Strategy

```bash
# Unit tests (fast)
uv run pytest tests/test_models.py -v              # 42 tests ✅

# Selector resolution tests (Sprint 2)
uv run pytest tests/test_selector_resolver.py -v   # ✅

# Integration tests (browser)
uv run pytest tests/test_browser.py -v --slow

# All tests
uv run pytest -v
```

---

## Success Criteria

| Criterion | Sprint | Status |
|-----------|--------|--------|
| Clean model architecture | 1 | ✅ |
| Codegen-style selectors | 1 | ✅ |
| Multi-selector capture | 1 | ✅ |
| Resilient playback | 2 | ✅ |
| Selector fallback chain | 2 | ✅ |
| Coordinate fallback | 2 | ✅ |
| Safe replay mode | 2 | ✅ |
| Chrome extension capture | 3 | ⏳ |
| iframe support | 3 | ⏳ |
| Video recording | 4 | ⏳ |
| LLM conversion | 4 | ⏳ |

---

## What Gets Removed (Clean Refactor)

| Old Code | Replacement | Status |
|----------|-------------|--------|
| `RecordedEvent` model | `UIEvent` | ✅ |
| `Workflow` model | `RecordingSession` | ✅ |
| `workflows/` directory | `sessions/` | ✅ |
| Single selector string | `SelectorCandidate[]` | ✅ |
| Screenshot capture | Video recording | ⏳ Sprint 4 |
