"""Convert raw browser recordings to ActionDefinitions using LLM analysis.

This module handles:
1. Loading sessions from JSON files (RecordingSession format)
2. Event preprocessing (collapsing noise, selecting best selectors)
3. Prompt loading from YAML
4. LLM invocation with structured output
5. Saving processed workflows
"""

import json
from pathlib import Path
from typing import Any

import yaml

from browser_agents.llm import get_structured_llm
from browser_agents.models import (
    ActionDefinition,
    RecordingSession,
    SelectorCandidate,
    UIEvent,
    UIEventType,
)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Limits for LLM context
MAX_EVENTS = 100
MIN_EVENTS = 2


def load_session(path: Path) -> RecordingSession:
    """Load a RecordingSession from a JSON file.

    Args:
        path: Path to the session.json file.

    Returns:
        RecordingSession object with metadata and events.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        ValueError: If the file is empty or malformed.
    """
    with path.open(encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        raise ValueError(f"Session file is empty: {path}")

    return RecordingSession.model_validate_json(content)


def get_best_selector(selectors: list[SelectorCandidate]) -> str | None:
    """Get the best selector value from a list of candidates.

    Priority: role > label > placeholder > text > testid > css

    Args:
        selectors: List of SelectorCandidate objects.

    Returns:
        Best selector value string, or None if list is empty.
    """
    if not selectors:
        return None

    # Priority order matches Playwright Codegen
    priority = {
        "role": 0,
        "label": 1,
        "placeholder": 2,
        "text": 3,
        "testid": 4,
        "css": 5,
    }

    # Sort by priority and confidence
    sorted_selectors = sorted(
        selectors,
        key=lambda s: (priority.get(s.strategy, 99), s.confidence != "high"),
    )

    best = sorted_selectors[0]

    # For role selectors, return a more usable format
    if best.strategy == "role" and best.role and best.name:
        return f'role={best.role}[name="{best.name}"]'

    return best.value


def preprocess_events(events: list[UIEvent]) -> list[dict[str, Any]]:
    """Preprocess UIEvents for LLM consumption.

    Transformations:
    - Select best selector from each event's selector list
    - Include element context (type, label, text) for LLM understanding
    - Remove scroll events (usually noise)
    - Deduplicate consecutive navigations to same URL
    - Collapse consecutive type events on same selector
    - Strip internal fields (id, timestamp, relative_time_ms)

    Args:
        events: List of UIEvent objects from a recording session.

    Returns:
        List of simplified event dicts suitable for LLM prompt.
    """
    processed: list[dict[str, Any]] = []
    current_type: dict[str, Any] | None = None

    for event in events:
        event_type = (
            event.event_type.value
            if isinstance(event.event_type, UIEventType)
            else event.event_type
        )

        # Get best selector
        selector = get_best_selector(event.selectors)

        # Collapse consecutive type events on same selector
        if event_type == "type":
            if current_type and current_type.get("selector") == selector:
                # Update to latest value
                current_type["value"] = event.value
            else:
                # Flush previous and start new
                if current_type:
                    processed.append(current_type)
                current_type = {
                    "event_type": "type",
                    "selector": selector,
                    "value": event.value,
                }
                # Add element context if available
                if event.element_label:
                    current_type["element_label"] = event.element_label
                if event.placeholder:
                    current_type["placeholder"] = event.placeholder
            continue

        # Flush pending type event
        if current_type:
            processed.append(current_type)
            current_type = None

        # Skip scroll events (usually noise)
        if event_type == "scroll":
            continue

        # Deduplicate consecutive navigations to same URL
        if event_type == "navigate":
            if (
                processed
                and processed[-1].get("event_type") == "navigate"
                and processed[-1].get("url") == event.url
            ):
                continue

        # Build event dict
        event_dict: dict[str, Any] = {"event_type": event_type}

        # Add selector if present
        if selector:
            event_dict["selector"] = selector

        # Add URL for navigate events
        if event.url and event_type == "navigate":
            event_dict["url"] = event.url

        # Add value for type, select_option, check events
        if event.value:
            event_dict["value"] = event.value

        # Add key for key_press events
        if event.key:
            event_dict["key"] = event.key

        # Add element context for LLM understanding
        if event.element_type and event.element_type != "generic":
            event_dict["element_type"] = event.element_type
        if event.element_text:
            event_dict["element_text"] = event.element_text[:100]  # Truncate
        if event.element_label:
            event_dict["element_label"] = event.element_label

        # Add fallback coordinates if no selector
        if not selector and event.x is not None and event.y is not None:
            event_dict["x"] = event.x
            event_dict["y"] = event.y

        # Note iframe context
        if event.frame_type == "iframe":
            event_dict["frame"] = "iframe"
            if event.frame_src:
                event_dict["frame_src"] = event.frame_src

        processed.append(event_dict)

    # Flush any remaining type event
    if current_type:
        processed.append(current_type)

    return processed


def load_prompt(prompt_name: str = "convert_session") -> dict[str, str]:
    """Load a conversion prompt from YAML file.

    Args:
        prompt_name: Name of prompt file (without .yaml extension).

    Returns:
        Dict with 'system_prompt' and 'user_template' keys.

    Raises:
        FileNotFoundError: If prompt file doesn't exist.
        ValueError: If prompt file has invalid format.
    """
    # Try new prompt first, fall back to old
    prompt_path = PROMPTS_DIR / f"{prompt_name}.yaml"
    if not prompt_path.exists():
        prompt_path = PROMPTS_DIR / "convert_recording.yaml"

    with prompt_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid prompt file: expected dict, got {type(data).__name__}"
        )

    return {k: str(v) for k, v in data.items()}


def save_action_definition(action: ActionDefinition, session_dir: Path) -> Path:
    """Save an ActionDefinition to the processed directory.

    Args:
        action: The ActionDefinition to save.
        session_dir: Path to the session directory.

    Returns:
        Path to the saved workflow.json file.
    """
    processed_dir = session_dir / "processed"
    processed_dir.mkdir(exist_ok=True)

    output_path = processed_dir / "workflow.json"
    with output_path.open("w", encoding="utf-8") as f:
        f.write(action.model_dump_json(indent=2))

    return output_path


async def convert_session_to_action(
    session: RecordingSession,
    description: str,
    max_retries: int = 2,
) -> ActionDefinition | str:
    """Convert a session's events to an ActionDefinition using LLM analysis.

    This function:
    1. Preprocesses events to reduce noise and select best selectors
    2. Validates event count (min 2, max 100)
    3. Sends to LLM with structured output
    4. Validates the response

    Args:
        session: The RecordingSession object to convert.
        description: User description of what the workflow does.
        max_retries: Number of retry attempts for transient failures.

    Returns:
        ActionDefinition on success, or error string on failure.

    Example:
        >>> session = load_session(Path("sessions/sess_abc/session.json"))
        >>> result = await convert_session_to_action(session, "Login and checkout")
        >>> if isinstance(result, ActionDefinition):
        ...     save_action_definition(result, Path("sessions/sess_abc"))
    """
    try:
        # Preprocess events
        events = preprocess_events(session.events)

        # Validate event count
        if len(events) < MIN_EVENTS:
            return f"Session too short: {len(events)} events (minimum {MIN_EVENTS})"

        if len(events) > MAX_EVENTS:
            events = events[:MAX_EVENTS]

        # Load prompt
        prompts = load_prompt()

        # Build events message
        events_content = prompts["user_template"].format(
            start_url=session.metadata.source_url,
            event_count=len(events),
            events_json=json.dumps(events, indent=2),
        )

        # Build messages: system instructions, user intent, then events
        messages: list[tuple[str, str]] = [
            ("system", prompts["system_prompt"]),
            ("user", f"I want to create a workflow that: {description}"),
            ("user", events_content),
        ]

        # Get structured LLM with retry
        llm = get_structured_llm(ActionDefinition)

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
        return f"Invalid JSON in session: {e}"
