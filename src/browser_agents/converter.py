"""Convert raw browser recordings to ActionDefinitions using LLM analysis.

This module handles:
1. Loading recordings from JSONL files
2. Event preprocessing (collapsing keystrokes, removing noise)
3. Prompt loading from YAML
4. LLM invocation with structured output
5. Retry and validation logic
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from browser_agents.llm import get_structured_llm
from browser_agents.models import ActionDefinition, RecordedEvent, Recording

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Limits for LLM context
MAX_EVENTS = 100
MIN_EVENTS = 2


def load_recording(path: Path) -> Recording:
    """Load a recording from a JSONL file.

    Args:
        path: Path to the .jsonl recording file.

    Returns:
        Recording object with metadata and events.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        ValueError: If the file is empty or malformed.
    """
    events: list[RecordedEvent] = []

    with path.open(encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        raise ValueError(f"Recording file is empty: {path}")

    # First line is metadata
    metadata = json.loads(lines[0])

    # Remaining lines are events
    for line in lines[1:]:
        if line.strip():
            events.append(RecordedEvent.model_validate_json(line))

    return Recording(
        session_id=metadata.get("session_id", "unknown"),
        start_url=metadata.get("start_url", "about:blank"),
        started_at=datetime.fromisoformat(metadata.get("started_at", "2000-01-01T00:00:00+00:00")),
        events=events,
    )


def preprocess_events(events: list[RecordedEvent]) -> list[dict[str, Any]]:
    """Collapse verbose events for LLM consumption.

    Transformations:
    - Merge consecutive type events on same selector (keep final value)
    - Remove scroll events (usually noise for action definitions)
    - Deduplicate consecutive navigations to same URL
    - Strip null fields and timestamps

    Args:
        events: List of raw RecordedEvent objects from a recording.

    Returns:
        List of simplified event dicts suitable for LLM prompt.

    Example:
        >>> events = [
        ...     RecordedEvent(timestamp=1.0, event_type="type", selector="#email", value="a"),
        ...     RecordedEvent(timestamp=1.1, event_type="type", selector="#email", value="ab"),
        ...     RecordedEvent(timestamp=1.2, event_type="type", selector="#email", value="abc"),
        ... ]
        >>> preprocess_events(events)
        [{'event_type': 'type', 'selector': '#email', 'value': 'abc'}]
    """
    processed: list[dict[str, Any]] = []
    current_type: dict[str, Any] | None = None

    for event in events:
        # Collapse consecutive type events on same selector
        if event.event_type == "type":
            if current_type and current_type.get("selector") == event.selector:
                # Update to latest value (overwrites previous)
                current_type["value"] = event.value
            else:
                # Flush previous type event and start new one
                if current_type:
                    processed.append(current_type)
                current_type = {
                    "event_type": "type",
                    "selector": event.selector,
                    "value": event.value,
                }
        else:
            # Flush pending type event
            if current_type:
                processed.append(current_type)
                current_type = None

            # Skip scroll events (usually noise)
            if event.event_type == "scroll":
                continue

            # Deduplicate consecutive navigations to same URL
            if event.event_type == "navigate":
                if processed and processed[-1].get("url") == event.url:
                    continue

            # Add event with non-null fields only (exclude timestamp)
            event_dict = {
                k: v for k, v in event.model_dump().items() if v is not None and k != "timestamp"
            }
            processed.append(event_dict)

    # Flush any remaining type event
    if current_type:
        processed.append(current_type)

    return processed


def load_prompt() -> dict[str, str]:
    """Load the conversion prompt from YAML file.

    Returns:
        Dict with 'system_prompt' and 'user_template' keys.

    Raises:
        FileNotFoundError: If prompt file doesn't exist.
        ValueError: If prompt file has invalid format.
    """
    prompt_path = PROMPTS_DIR / "convert_recording.yaml"
    with prompt_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid prompt file: expected dict, got {type(data).__name__}")

    return {k: str(v) for k, v in data.items()}


async def convert_recording_to_action(
    recording: Recording,
    max_retries: int = 2,
    temperature: float = 0.0,
) -> ActionDefinition | str:
    """Convert a raw recording to an ActionDefinition using LLM analysis.

    This function:
    1. Preprocesses events to reduce noise
    2. Validates event count (min 2, max 100)
    3. Sends to LLM with structured output
    4. Validates the response

    Args:
        recording: The Recording object to convert.
        max_retries: Number of retry attempts for transient failures.
        temperature: LLM temperature (0.0 = deterministic).

    Returns:
        ActionDefinition on success, or error string on failure.

    Example:
        >>> from browser_agents.playback import load_recording
        >>> recording = load_recording(Path("recordings/abc.jsonl"))
        >>> result = await convert_recording_to_action(recording)
        >>> if isinstance(result, ActionDefinition):
        ...     print(f"Created action: {result.name}")
    """
    try:
        # Preprocess events
        events = preprocess_events(recording.events)

        # Validate event count
        if len(events) < MIN_EVENTS:
            return f"Recording too short: {len(events)} events (minimum {MIN_EVENTS})"

        if len(events) > MAX_EVENTS:
            events = events[:MAX_EVENTS]

        # Load prompt
        prompts = load_prompt()

        # Build messages
        user_content = prompts["user_template"].format(
            start_url=recording.start_url,
            event_count=len(events),
            events_json=json.dumps(events, indent=2),
        )

        messages: list[tuple[str, str]] = [
            ("system", prompts["system_prompt"]),
            ("user", user_content),
        ]

        # Get structured LLM with retry
        llm = get_structured_llm(ActionDefinition, temperature=temperature)

        # Apply retry for transient errors
        retryable = llm.with_retry(
            retry_if_exception_type=(ConnectionError, TimeoutError),
            stop_after_attempt=max_retries,
        )

        # Invoke LLM
        result = await retryable.ainvoke(messages)

        # Validate response
        if result is None:
            return "LLM returned empty response"

        if not isinstance(result, ActionDefinition):
            return f"Unexpected response type: {type(result).__name__}"

        if not result.name or not result.steps:
            return "LLM returned incomplete ActionDefinition (missing name or steps)"

        return result

    except FileNotFoundError as e:
        return f"Prompt file not found: {e}"
    except ValueError as e:
        return f"Invalid prompt format: {e}"
    except (ConnectionError, TimeoutError) as e:
        return f"LLM connection failed: {e}"
    except json.JSONDecodeError as e:
        return f"Invalid JSON in recording: {e}"
