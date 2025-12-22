# Phase 3 Implementation Plan: Recording → Action Conversion

## Goal

Convert raw browser recordings into clean, parameterized action definitions using LLM analysis. Support model swapping between local (Ollama) and cloud (Anthropic/OpenAI) providers.

## Architecture

```
Recording (JSONL)
    ↓
Load → Recording Pydantic model
    ↓
get_llm() → BaseChatModel.with_structured_output(ActionDefinition)
    ↓
ActionDefinition (guaranteed valid Pydantic)
    ↓
JSON Storage (actions/*.json)
```

## Key Design Decisions

### 1. Structured Output (not "output JSON" prompts)

Use LangChain's `with_structured_output()` method instead of asking the LLM to "output JSON":

```python
# Bad: Manual JSON parsing, fragile
response = await llm.ainvoke("Output JSON matching this schema...")
data = json.loads(response.content)  # Can fail!

# Good: Guaranteed Pydantic output
llm = get_llm().with_structured_output(ActionDefinition)
result = await llm.ainvoke(messages)  # Returns ActionDefinition directly
```

### 2. Rich Field Descriptions

Guide the LLM with Pydantic `Field(description=...)`:

```python
class ActionDefinition(BaseModel):
    name: str = Field(
        description="Action name in snake_case (e.g., 'login_user', 'add_to_cart')"
    )
    steps: list[ActionStep] = Field(
        description="Ordered list of steps (3-10 steps, not raw events)"
    )
```

### 3. External YAML Prompts

Store prompts externally for easy iteration:

```yaml
# src/browser_agents/prompts/convert_recording.yaml
system_prompt: |
  You are a browser automation analyst...

user_template: |
  Convert this recording:
  **Start URL:** {start_url}
  **Events:** {events_json}
```

### 4. Proper Provider Support

Use dedicated clients per provider:

| Provider | Client | Notes |
|----------|--------|-------|
| Ollama | `ChatOpenAI` with base_url | OpenAI-compatible /v1 endpoint |
| Anthropic | `ChatAnthropic` | Dedicated client (ChatOpenAI won't work) |
| OpenAI | `ChatOpenAI` | Native client |

---

## Dependencies to Add

```toml
# pyproject.toml
dependencies = [
    "pydantic-settings>=2.7.0",     # .env configuration
    "langchain-core>=0.3.0",        # LLM abstractions
    "langchain-openai>=0.3.0",      # Ollama + OpenAI
    "langchain-anthropic>=0.3.0",   # Anthropic (dedicated)
    "httpx>=0.28.0",                # HTTP client
    "pyyaml>=6.0.0",                # Prompt loading
]
```

---

## Files to Create

### `src/browser_agents/config.py`

```python
from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = Field(default="ollama")

    # Ollama
    ollama_url: HttpUrl = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="qwen2.5:7b")

    # Anthropic
    anthropic_api_key: str | None = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-4")

    # OpenAI
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o")


settings = Settings()
```

### `src/browser_agents/llm.py`

```python
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from browser_agents.config import settings


def get_llm(temperature: float = 0.0) -> BaseChatModel:
    provider = settings.llm_provider.lower()

    if provider == "ollama":
        return ChatOpenAI(
            model=settings.ollama_model,
            base_url=f"{str(settings.ollama_url).rstrip('/')}/v1",
            api_key=SecretStr("ollama"),
            temperature=temperature,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=SecretStr(settings.anthropic_api_key),
            temperature=temperature,
        )

    elif provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=SecretStr(settings.openai_api_key),
            temperature=temperature,
        )

    raise ValueError(f"Unknown provider: {provider}")


def get_structured_llm(schema: type, temperature: float = 0.0) -> BaseChatModel:
    """Get LLM configured for structured Pydantic output."""
    return get_llm(temperature).with_structured_output(schema)
```

### `src/browser_agents/models.py` (additions)

```python
class ActionParameter(BaseModel):
    """A parameter for action substitution."""
    name: str = Field(description="Parameter name in snake_case")
    description: str = Field(description="What this parameter represents")
    example: str = Field(description="Example value")


class ActionStep(BaseModel):
    """A single step in the workflow."""
    action: str = Field(description="Action: navigate, click, type, scroll, wait")
    target: str | None = Field(default=None, description="CSS selector or URL")
    value: str | None = Field(default=None, description="Value with {param} placeholders")
    description: str = Field(description="Human-readable step description")


class ActionDefinition(BaseModel):
    """A reusable browser action from a recording."""
    name: str = Field(description="Action name in snake_case")
    description: str = Field(description="What this action accomplishes")
    parameters: list[ActionParameter] = Field(description="Required parameters")
    steps: list[ActionStep] = Field(description="Steps to execute (3-10)")
    domains: list[str] = Field(description="Allowed domains for safety")
```

### `src/browser_agents/prompts/convert_recording.yaml`

```yaml
system_prompt: |
  You are a browser automation analyst. Convert raw recordings into
  clean, reusable action definitions.

  ## Guidelines

  **Naming:** Use descriptive snake_case (login_user, add_to_cart)

  **Parameters:** Extract variable values (emails, names, quantities).
  Do NOT parameterize URLs, selectors, or button labels.
  Use {param_name} syntax in step values.

  **Steps:** Combine raw events into 3-10 logical steps.
  Focus on user intent, not browser mechanics.

  **Domains:** List unique domains for safety validation.

user_template: |
  Convert this recording:

  **Start URL:** {start_url}
  **Events:** {event_count}

  {events_json}
```

### `src/browser_agents/converter.py`

```python
import json
import yaml
from pathlib import Path

from browser_agents.llm import get_structured_llm
from browser_agents.models import ActionDefinition, Recording


PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt() -> dict[str, str]:
    with (PROMPTS_DIR / "convert_recording.yaml").open() as f:
        return yaml.safe_load(f)


async def convert_recording_to_action(
    recording: Recording,
    temperature: float = 0.0,
) -> ActionDefinition | str:
    """Convert recording to ActionDefinition using structured output."""
    try:
        prompts = load_prompt()

        # Summarize events for LLM
        events = [
            {k: v for k, v in e.model_dump().items() if v is not None}
            for e in recording.events
        ]

        messages = [
            ("system", prompts["system_prompt"]),
            ("user", prompts["user_template"].format(
                start_url=recording.start_url,
                event_count=len(recording.events),
                events_json=json.dumps(events, indent=2),
            )),
        ]

        llm = get_structured_llm(ActionDefinition, temperature)
        return await llm.ainvoke(messages)

    except Exception as e:
        return f"Conversion failed: {e}"
```

### CLI Addition (`src/browser_agents/cli.py`)

```python
@app.command()
def convert(
    recording: Path = typer.Argument(...),
    output_dir: Path = typer.Option(Path("actions"), "-o"),
    model: str | None = typer.Option(None, "-m"),
    temperature: float = typer.Option(0.0, "-t"),
) -> None:
    """Convert recording to reusable action definition."""
    # Load, convert, save...
```

---

## Usage

```bash
# Local model (default)
uv run browser-agents convert recordings/abc.jsonl

# Override model
uv run browser-agents convert recordings/abc.jsonl --model claude-sonnet-4

# Via environment
LLM_PROVIDER=anthropic uv run browser-agents convert recordings/abc.jsonl
```

---

## Best Practices Applied

1. **Structured output** - `with_structured_output()` over "output JSON" prompts
2. **Rich Field descriptions** - Guide LLM with Pydantic metadata
3. **External prompts** - YAML files for easy iteration
4. **Proper providers** - langchain-anthropic for Anthropic
5. **Error strings** - Return errors for LLM-recoverable failures
6. **Temperature 0.0** - Deterministic output

---

## File Summary

| File | Purpose |
|------|---------|
| `config.py` | Pydantic Settings for .env |
| `llm.py` | LLM factory with structured output |
| `converter.py` | Recording → ActionDefinition |
| `prompts/convert_recording.yaml` | External prompt |
| `models.py` | Add ActionDefinition models |
| `cli.py` | Add convert command |
| `.env.example` | Configuration template |
