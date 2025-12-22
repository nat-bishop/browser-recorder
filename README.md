# browser-agents

Record browser interactions and convert them to AI agent tools.

## Quick Start

```bash
# Install dependencies
uv sync --extra dev

# Install Playwright browsers
uv run playwright install chromium

# Record a session (saves to workflows/<session-id>/workflow.json)
uv run browser-agents record https://example.com

# Record with name and description
uv run browser-agents record https://example.com --name "login-flow" --description "Login to example.com"

# Replay raw events from a workflow
uv run browser-agents replay workflows/<session-id>/workflow.json

# Visual demo mode with cursor indicator and smooth movement
uv run browser-agents replay workflows/<session-id>/workflow.json --demo

# Demo mode with custom timing
uv run browser-agents replay workflows/<session-id>/workflow.json --demo --delay 0.5 --speed 30

# Convert workflow events to action definition (requires Ollama)
# Can run multiple times to create multiple action interpretations
uv run browser-agents convert workflows/<session-id>/workflow.json -d "Login and navigate to dashboard"

# List all workflows with their names and actions
uv run browser-agents list

# Replay action steps with parameter substitution
uv run browser-agents replay workflows/<session-id>/workflow.json --action
uv run browser-agents replay workflows/<session-id>/workflow.json --action --param username=foo --param password=bar

# Replay a specific action by name (when workflow has multiple actions)
uv run browser-agents replay workflows/<session-id>/workflow.json --action --name login_user

# Guided mode: interactive error handling with LLM diagnosis
uv run browser-agents replay workflows/<session-id>/workflow.json --action --guided
```

## Workflow Format

Browser-agents uses a unified `Workflow` JSON format (v2) stored in `workflows/<session-id>/workflow.json`:

- **Metadata**: `name`, `description`, `version` for identification and migrations
- **Raw events**: Captured browser interactions (clicks, typing, navigation)
- **Actions list**: Multiple LLM-derived parameterized action definitions (added by `convert`)
- **Media refs**: Optional video/audio references (future)

This single-file format enables provenance tracking (raw events are preserved alongside derived actions). Multiple action interpretations can be stored for the same recording.

## Development

See [CLAUDE.md](CLAUDE.md) for development guidelines and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.
