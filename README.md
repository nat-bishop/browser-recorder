# browser-agents

Records browser interactions via a Chrome extension, replays them with Playwright, and uses an LLM pipeline to convert raw recordings into parameterized, reusable automation definitions.

A user records themselves logging into a site — 47 raw events including every keystroke, scroll, and redirect — and the system produces a clean 4-step `ActionDefinition` with extracted `{{email}}` and `{{password}}` parameters, domain constraints, and risk annotations from the network traffic it observed.

## How It Works

**Record** — A [playwright-crx](https://github.com/nicolo-ribaudo/playwright-crx) Chrome extension captures user actions and network traffic as a `trace.zip` (NDJSON events + screenshots + DOM snapshots). The importer (`importers/trace_importer.py`) parses Playwright's internal selector format into portable strategies — ARIA roles, labels, placeholders, test IDs, and CSS fallbacks.

**Replay** — `SessionExecutor` (`playback/executor.py`) replays all 11 event types (click, type, navigate, select, check, key press, etc.) through Playwright's async `locator()` API. `SafeReplayController` (`playback/safe_replay.py`) intercepts outgoing requests with four modes — `live`, `warn`, `block`, `mock` — to prevent state-changing HTTP methods during replay.

**Convert** — A multi-stage pipeline preprocesses recorded events, correlates them with captured network requests, enriches the result with risk analysis, and sends everything to an LLM that returns structured, validated output. This is the core of the project and is described in detail below.

## LLM Conversion Pipeline

The conversion runs through five stages, each solving a distinct problem:

**1. Event Preprocessing** — `preprocess_events()` in `converter.py` reduces noise before anything reaches the LLM. Consecutive keystrokes on the same selector collapse into a single `type` event. Scroll events are removed. Duplicate navigations to the same URL are deduplicated. A recording with 100+ raw events typically reduces to ~10 logical steps.

**2. Network Correlation** — `correlation.py` links each UI event to the HTTP requests it triggered using a timestamp-window algorithm (2-second window, bounded by the next event). `filter_network_requests()` first strips static assets and known analytics domains (Google Analytics, Segment, Mixpanel, Hotjar, Sentry, etc.). Then `compute_risk()` classifies each correlated action:

| Level | Signals |
|-------|---------|
| `HIGH` | DELETE methods, URL patterns like `/payment`, `/checkout`, `/admin`, `/delete`, `/transfer` (12 patterns), credit card or SSN patterns in response bodies |
| `MEDIUM` | URL patterns like `/auth`, `/login`, `/password`, `/settings`, `/account` (10 patterns) |
| `LOW` | POST/PUT/PATCH without dangerous patterns |
| `NONE` | GET requests, static pages |

Risk levels accumulate from HTTP methods, URL regex patterns, and response body content inspection — a single action can match multiple signals.

**3. Event Enrichment** — `enrich_events_with_network()` in `converter.py` annotates each preprocessed event with `triggered_api_calls`, `risk_level`, `risk_reason`, and `is_state_changing`. Instead of seeing "clicked Submit," the LLM sees "clicked Submit -> POST /api/login (MEDIUM risk, auth endpoint)." Events are matched to their correlated actions by `_event_id`, which survives preprocessing and is stripped before the prompt is assembled.

**4. Structured Output** — `get_structured_llm()` in `llm.py` wraps a LangChain `BaseChatModel` with `.with_structured_output(ActionDefinition)`, which uses tool calling to enforce the Pydantic schema. The LLM returns a validated `ActionDefinition` instance — not raw text that needs parsing. The factory uses `ChatOpenAI` pointed at Ollama's OpenAI-compatible `/v1` endpoint (chosen over `ChatOllama` to avoid tool_call_id serialization bugs with Qwen/Llama models). Transient failures retry automatically via `with_retry()`.

**5. Prompt Design** — The prompt template (`prompts/convert_session.yaml`) has two sections: a system prompt defining event type semantics, selector reliability ranking, parameter extraction rules, and network context interpretation; and a user template with a one-shot example followed by the recording data. Network activity summaries — API endpoints used, state-changing operation counts, high-risk warnings — are appended to give the LLM a global view.

## Example Output

A recorded login session converts to:

```json
{
  "name": "login_user",
  "description": "Log into the application with email and password",
  "parameters": [
    {"name": "email", "description": "User email address", "example": "user@test.com", "is_sensitive": false},
    {"name": "password", "description": "User password", "example": "secret123", "is_sensitive": true}
  ],
  "steps": [
    {"action": "navigate", "target": "https://example.com/login", "description": "Go to login page"},
    {"action": "type", "target": "role=textbox[name=\"Email\"]", "value": "{{email}}", "description": "Enter email"},
    {"action": "type", "target": "role=textbox[name=\"Password\"]", "value": "{{password}}", "description": "Enter password"},
    {"action": "click", "target": "role=button[name=\"Sign In\"]", "description": "Submit login form"}
  ],
  "domains": ["example.com"]
}
```

Extracted parameters use `{{placeholder}}` syntax. Sensitive fields are flagged. Selectors prefer ARIA roles over CSS. The `domains` list constrains where the automation can run.

## Type System

Pydantic models define the data at each pipeline stage:

- **Recording**: `UIEvent` (11 event types with element context — type, label, text, placeholder), `NetworkRequest` (HAR-format HTTP traffic with response bodies up to 100KB), `RecordingSession` (metadata + events + network)
- **Correlation**: `CorrelatedAction` (UI event + triggered requests + API endpoints + `RiskLevel` as `IntEnum`)
- **Output**: `ActionDefinition` with parameterized `ActionStep`s, `ActionParameter` (with `is_sensitive` flag), and a `domains` whitelist

Validation runs at system boundaries: trace import, session deserialization (`model_validate_json`), LLM structured output, and config loading.

## Safety

Replay safety is enforced at the network layer. `SafeReplayController` registers a Playwright route handler that inspects each request's method. GET/HEAD/OPTIONS always pass; POST/PUT/PATCH/DELETE are handled according to the selected mode (warn and log, abort, or return mock 200 responses).

During conversion, `compute_risk()` flags dangerous operations before they become automation steps. `ActionParameter.is_sensitive` marks password and token fields. `ActionDefinition.domains` constrains where the generated automation is allowed to run.

## Getting Started

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js (for building the recorder extension).

```bash
uv sync --extra dev
uv run playwright install chromium

# Build the recorder extension (one-time)
cd recorder && npm install && npm run build && cd ..

# Launch Chrome with the recorder loaded
uv run browser-agents launch-chrome --url https://example.com
```

Record with Shift+Alt+R, save the trace, then import and convert:

```bash
uv run browser-agents import-trace ~/Downloads/trace.zip
uv run browser-agents convert-session sessions/sess_abc123 -d "Login and checkout"
```

See [CLAUDE.md](CLAUDE.md) for development setup, testing, and CLI reference. See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed data flows and design decisions.

## Project Layout

```
src/browser_agents/
  cli.py              # Typer CLI — record, replay, convert, list
  converter.py        # 5-stage LLM conversion pipeline
  correlation.py      # Event-network linking, risk detection
  llm.py              # LLM factory with structured output via tool calling
  config.py           # Pydantic-settings (.env support)
  models/             # UIEvent, NetworkRequest, RecordingSession, ActionDefinition
  playback/           # SessionExecutor (11 event types), SafeReplayController
  storage/            # Session persistence (JSON + trace archives)
  importers/          # Playwright trace.zip parser
  prompts/            # YAML prompt templates
recorder/             # playwright-crx Chrome extension (TypeScript/React)
tests/                # pytest suite (models, CLI, preprocessing, correlation)
```
