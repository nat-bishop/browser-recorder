"""Convert raw browser recordings to ActionDefinitions using LLM analysis.

This module handles:
1. Loading sessions from JSON files (RecordingSession format)
2. Event preprocessing (collapsing noise, selecting best selectors)
3. Network correlation (linking events to API calls)
4. Prompt loading from YAML
5. LLM invocation with structured output
6. Saving processed workflows
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from browser_agents.llm import get_structured_llm
from browser_agents.models import (
    ActionDefinition,
    RecordingSession,
    UIEvent,
    UIEventType,
)

if TYPE_CHECKING:
    from browser_agents.models import CorrelatedAction

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


def preprocess_events(events: list[UIEvent]) -> list[dict[str, Any]]:
    """Preprocess UIEvents for LLM consumption.

    Transformations:
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

        # Use selector directly
        selector = event.selector

        # Collapse consecutive type events on same selector
        if event_type == "type":
            if current_type and current_type.get("selector") == selector:
                # Update to latest value (keep first event's ID for correlation)
                current_type["value"] = event.value
            else:
                # Flush previous and start new
                if current_type:
                    processed.append(current_type)
                current_type = {
                    "_event_id": event.id,  # Store event ID for correlation
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

        # Build event dict with event ID for correlation
        event_dict: dict[str, Any] = {
            "_event_id": event.id,  # Store event ID for correlation
            "event_type": event_type,
        }

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


def enrich_events_with_network(
    preprocessed_events: list[dict[str, Any]],
    correlated_actions: list["CorrelatedAction"],
) -> list[dict[str, Any]]:
    """Enrich preprocessed events with network request information.

    Matches preprocessed events to correlated actions by event ID and adds
    network context (triggered requests, risk level) to each event.

    Args:
        preprocessed_events: Events from preprocess_events() (must have _event_id)
        correlated_actions: Correlated actions from correlate_events_with_network()

    Returns:
        Enriched event dicts with network context added
    """
    from browser_agents.models import RiskLevel

    # Build lookup by event ID for accurate matching
    # This handles preprocessing that removes events (scroll, duplicate navigates)
    action_by_event_id: dict[str, CorrelatedAction] = {
        a.event.id: a for a in correlated_actions if a.event is not None
    }

    enriched = []
    for event in preprocessed_events:
        enriched_event = event.copy()

        # Match by event ID (set during preprocess_events)
        event_id = event.get("_event_id")
        if event_id and event_id in action_by_event_id:
            action = action_by_event_id[event_id]

            # Add triggered API calls (not page loads)
            api_requests = [
                {"method": r.method, "url": r.url, "status": r.status}
                for r in action.network_requests
                if r.mime_type and "json" in r.mime_type.lower()
            ]
            if api_requests:
                enriched_event["triggered_api_calls"] = api_requests

            # Add risk level if not NONE
            if action.risk_level != RiskLevel.NONE:
                enriched_event["risk_level"] = action.risk_level.value
                if action.risk_reason:
                    enriched_event["risk_reason"] = action.risk_reason

            # Add state-changing flag
            if action.is_state_changing:
                enriched_event["is_state_changing"] = True

        # Remove internal _event_id before sending to LLM
        enriched_event.pop("_event_id", None)
        enriched.append(enriched_event)

    return enriched


def build_network_summary(correlated_actions: list["CorrelatedAction"]) -> str:
    """Build a summary of network activity for the LLM.

    Args:
        correlated_actions: List of correlated actions

    Returns:
        Human-readable summary of network activity
    """
    from browser_agents.models import RiskLevel

    # Collect unique API endpoints and their methods
    api_calls: dict[str, set[str]] = {}
    high_risk: list[str] = []
    state_changing_count = 0

    for action in correlated_actions:
        if action.is_state_changing:
            state_changing_count += 1

        if action.risk_level == RiskLevel.HIGH:
            if action.risk_reason:
                high_risk.append(action.risk_reason)

        for req in action.network_requests:
            if req.mime_type and "json" in req.mime_type.lower():
                # Extract path from URL
                from urllib.parse import urlparse

                try:
                    path = urlparse(req.url).path
                    if path not in api_calls:
                        api_calls[path] = set()
                    api_calls[path].add(req.method)
                except Exception:
                    pass

    if not api_calls and not high_risk:
        return "No significant API calls detected during this recording."

    lines = []

    if api_calls:
        lines.append("**API Endpoints Used:**")
        for path, methods in sorted(api_calls.items())[:10]:  # Limit to 10
            methods_str = ", ".join(sorted(methods))
            lines.append(f"- {methods_str} {path}")

    if state_changing_count > 0:
        lines.append(f"\n**State-changing operations:** {state_changing_count}")

    if high_risk:
        lines.append("\n**High-risk operations detected:**")
        lines.extend(f"- {reason}" for reason in high_risk[:5])

    return "\n".join(lines)


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
    prompt_path = PROMPTS_DIR / f"{prompt_name}.yaml"

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
    include_network: bool = True,
) -> ActionDefinition | str:
    """Convert a session's events to an ActionDefinition using LLM analysis.

    This function:
    1. Preprocesses events to reduce noise and select best selectors
    2. Correlates events with network requests (optional)
    3. Validates event count (min 2, max 100)
    4. Sends to LLM with structured output
    5. Validates the response

    Args:
        session: The RecordingSession object to convert.
        description: User description of what the workflow does.
        max_retries: Number of retry attempts for transient failures.
        include_network: Whether to include network correlation context.

    Returns:
        ActionDefinition on success, or error string on failure.

    Example:
        >>> session = load_session(Path("sessions/sess_abc/session.json"))
        >>> result = await convert_session_to_action(session, "Login and checkout")
        >>> if isinstance(result, ActionDefinition):
        ...     save_action_definition(result, Path("sessions/sess_abc"))
    """
    from browser_agents.correlation import (
        correlate_events_with_network,
        filter_network_requests,
    )

    try:
        # Preprocess events
        events = preprocess_events(session.events)

        # Validate event count
        if len(events) < MIN_EVENTS:
            return f"Session too short: {len(events)} events (minimum {MIN_EVENTS})"

        if len(events) > MAX_EVENTS:
            events = events[:MAX_EVENTS]

        # Correlate with network requests if enabled and available
        network_summary = ""
        if include_network and session.network_requests:
            filtered_requests = filter_network_requests(session.network_requests)
            correlated_actions = correlate_events_with_network(
                session.events,
                filtered_requests,
                session.metadata.started_at,
            )

            # Enrich events with network context
            events = enrich_events_with_network(events, correlated_actions)

            # Build network summary for LLM
            network_summary = build_network_summary(correlated_actions)

        # Load prompt
        prompts = load_prompt()

        # Build events message
        events_content = prompts["user_template"].format(
            start_url=session.metadata.source_url,
            event_count=len(events),
            events_json=json.dumps(events, indent=2),
        )

        # Add network summary if available
        if network_summary:
            events_content += f"\n\n**Network Activity:**\n{network_summary}"

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
