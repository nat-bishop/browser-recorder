"""Import recordings from playwright-crx trace.zip files."""

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from browser_agents.models import (
    NetworkRequest,
    RecordingSession,
    SessionMetadata,
    UIEvent,
    UIEventType,
)

# Mapping from Playwright methods to UIEventType
METHOD_MAP: dict[str, UIEventType] = {
    "click": UIEventType.CLICK,
    "dblclick": UIEventType.DOUBLE_CLICK,
    "fill": UIEventType.TYPE,
    "clear": UIEventType.CLEAR,
    "check": UIEventType.CHECK,
    "uncheck": UIEventType.UNCHECK,
    "selectOption": UIEventType.SELECT_OPTION,
    "press": UIEventType.KEY_PRESS,
    "goto": UIEventType.NAVIGATE,
    "scroll": UIEventType.SCROLL,
}


def _strip_quotes(text: str) -> str:
    """Remove surrounding quotes from text."""
    return text.strip("\"'")


def _extract_quoted_value(text: str, prefix: str) -> str:
    """Extract value from quoted string like name="value" or name='value'."""
    for quote in ('"', "'"):
        pattern = f"{prefix}{quote}"
        if pattern in text:
            start = text.find(pattern) + len(pattern)
            end = text.rfind(quote)
            return text[start:end] if end > start else ""
    # Fallback for unquoted
    return text.split(f"{prefix}")[1].rstrip("]")


def parse_playwright_selector(selector: str) -> str | None:
    """Convert Playwright internal selector to a Playwright locator string.

    Playwright uses internal selector formats that need conversion:
    - internal:role=button[name="Submit"] -> role=button[name="Submit"]
    - internal:label="Email" -> label="Email"
    - internal:text="Click me" -> text="Click me"
    - CSS selectors pass through as-is

    Args:
        selector: Playwright internal selector string

    Returns:
        Playwright locator string or None if empty
    """
    if not selector:
        return None

    # Handle internal: prefixed selectors by converting to Playwright format
    if selector.startswith("internal:role="):
        value_part = selector[14:]
        if "[name=" in value_part:
            role = value_part.split("[")[0]
            name = _extract_quoted_value(value_part, "name=")
            return f'role={role}[name="{name}"]'
        return f"role={value_part}"

    if selector.startswith("internal:label="):
        return f"label={_strip_quotes(selector[15:])}"

    if selector.startswith("internal:text="):
        return f"text={_strip_quotes(selector[14:])}"

    if selector.startswith("internal:testid="):
        return f"data-testid={_strip_quotes(selector[16:])}"

    if selector.startswith("internal:attr="):
        return f"[{selector[14:]}]"

    # Return as-is for CSS selectors
    return selector


def _parse_network_requests(network_data: str) -> list[NetworkRequest]:
    """Parse trace.network NDJSON into NetworkRequest objects.

    The trace.network file uses HAR (HTTP Archive) format with NDJSON entries.
    Each entry has type="resource-snapshot" with request/response details.

    Args:
        network_data: Raw NDJSON content from trace.network

    Returns:
        List of NetworkRequest objects
    """
    requests: list[NetworkRequest] = []

    for line in network_data.splitlines():
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if entry.get("type") != "resource-snapshot":
            continue

        snapshot = entry.get("snapshot", {})
        request = snapshot.get("request", {})
        response = snapshot.get("response", {})

        # Parse timestamp
        started_datetime = snapshot.get("startedDateTime", "")
        try:
            timestamp = datetime.fromisoformat(started_datetime.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            timestamp = datetime.now(tz=UTC)

        # Convert headers list to dict (skip entries missing name or value)
        request_headers = {
            h["name"]: h["value"]
            for h in request.get("headers", [])
            if "name" in h and "value" in h
        }
        response_headers = {
            h["name"]: h["value"]
            for h in response.get("headers", [])
            if "name" in h and "value" in h
        }

        # Get content info
        content = response.get("content", {})

        network_request = NetworkRequest(
            timestamp=timestamp,
            method=request.get("method", "GET"),
            url=request.get("url", ""),
            status=response.get("status"),
            status_text=response.get("statusText"),
            duration_ms=snapshot.get("time"),
            mime_type=content.get("mimeType"),
            request_headers=request_headers,
            response_headers=response_headers,
            request_body_size=request.get("bodySize"),
            response_body_size=response.get("bodySize"),
        )
        requests.append(network_request)

    return requests


def import_trace(trace_path: Path) -> RecordingSession:
    """Import a Playwright trace.zip into a RecordingSession.

    Supports both:
    - playwright-crx format: type="action", class="Locator"/"Page"/"Keyboard"
    - Playwright native format: type="before", class="Frame"

    The trace.zip file contains:
    - trace.trace: NDJSON file with action events
    - trace.network: NDJSON file with network events
    - resources/: Screenshots, DOM snapshots, etc.

    Args:
        trace_path: Path to the trace.zip file

    Returns:
        RecordingSession with imported events

    Raises:
        FileNotFoundError: If trace_path doesn't exist
        zipfile.BadZipFile: If file is not a valid zip
        KeyError: If trace.trace is missing from zip
    """
    events: list[UIEvent] = []
    network_requests: list = []
    base_time_ms: float | None = None  # For relative timestamps
    source_url: str = ""

    # Valid class names by trace format
    valid_classes = {
        "action": {"Locator", "Page", "Keyboard"},  # playwright-crx
        "before": {"Frame", "Locator", "Page", "Keyboard"},  # native Playwright
    }

    with zipfile.ZipFile(trace_path) as z:
        # Parse trace.network if present
        try:
            network_data = z.read("trace.network").decode("utf-8")
            network_requests = _parse_network_requests(network_data)
        except KeyError:
            pass  # No network data in this trace

        # Parse trace.trace (NDJSON format)
        trace_data = z.read("trace.trace").decode("utf-8")

        for line in trace_data.splitlines():
            if not line.strip():
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # Skip malformed lines

            entry_type = entry.get("type", "")
            if entry_type not in valid_classes:
                continue

            class_name = entry.get("class", "")
            if class_name not in valid_classes[entry_type]:
                continue

            method = entry.get("method", "")
            event_type = METHOD_MAP.get(method)
            if not event_type:
                continue

            params = entry.get("params", {})
            start_time_ms = entry.get("startTime", 0)

            if base_time_ms is None:
                base_time_ms = start_time_ms

            # Timestamp: native format uses wallTime, crx uses startTime directly
            wall_time = entry.get("wallTime")
            if wall_time:
                timestamp = datetime.fromtimestamp(wall_time / 1000, tz=UTC)
            elif entry_type == "action":
                timestamp = datetime.fromtimestamp(start_time_ms / 1000, tz=UTC)
            else:
                timestamp = datetime.now(tz=UTC)

            if method == "goto":
                source_url = params.get("url", source_url)

            events.append(
                UIEvent(
                    id=str(uuid4()),
                    timestamp=timestamp,
                    relative_time_ms=int(start_time_ms - base_time_ms),
                    event_type=event_type,
                    url=source_url,
                    selector=parse_playwright_selector(params.get("selector", "")),
                    value=params.get("value"),
                    key=params.get("key"),
                )
            )

    # Create session
    session_id = f"sess_{uuid4().hex[:12]}"
    now = datetime.now(tz=UTC)
    start_time = events[0].timestamp if events else now
    end_time = events[-1].timestamp if events else now
    duration_ms = events[-1].relative_time_ms if events else 0

    return RecordingSession(
        metadata=SessionMetadata(
            id=session_id,
            version=1,
            started_at=start_time,
            ended_at=end_time,
            duration_ms=duration_ms,
            source_url=source_url,
        ),
        events=events,
        network_requests=network_requests,
    )
