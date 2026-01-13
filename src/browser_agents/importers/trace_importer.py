"""Import recordings from playwright-crx trace.zip files."""

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from browser_agents.models import (
    RecordingSession,
    SelectorCandidate,
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


def parse_playwright_selector(selector: str) -> list[SelectorCandidate]:
    """Convert Playwright internal selector to SelectorCandidate list.

    Playwright uses internal selector formats like:
    - internal:role=button[name="Submit"]
    - internal:label="Email"
    - internal:text="Click me"
    - CSS selectors as fallback

    Args:
        selector: Playwright internal selector string

    Returns:
        List of SelectorCandidate objects
    """
    candidates: list[SelectorCandidate] = []

    if not selector:
        return candidates

    # Playwright uses internal:role=button[name="Submit"] format
    if selector.startswith("internal:role="):
        role_part = selector[14:]  # Remove "internal:role="
        # Parse role and name
        if "[name=" in role_part:
            role = role_part.split("[")[0]
            # Extract name using find/rfind to handle special chars properly
            if 'name="' in role_part:
                start = role_part.find('name="') + 6
                end = role_part.rfind('"')
                name = role_part[start:end] if end > start else ""
            elif "name='" in role_part:
                start = role_part.find("name='") + 6
                end = role_part.rfind("'")
                name = role_part[start:end] if end > start else ""
            else:
                name = role_part.split("[name=")[1].rstrip("]")
            candidates.append(
                SelectorCandidate(
                    strategy="role",
                    value=f'{role}[name="{name}"]',
                    confidence="high",
                    role=role,
                    name=name,
                )
            )
        else:
            # Just role without name
            candidates.append(
                SelectorCandidate(
                    strategy="role",
                    value=role_part,
                    confidence="medium",
                    role=role_part,
                )
            )
    elif selector.startswith("internal:label="):
        label = selector[15:].strip("\"'")
        candidates.append(
            SelectorCandidate(
                strategy="label",
                value=label,
                confidence="high",
            )
        )
    elif selector.startswith("internal:text="):
        text = selector[14:].strip("\"'")
        candidates.append(
            SelectorCandidate(
                strategy="text",
                value=text,
                confidence="medium",
            )
        )
    elif selector.startswith("internal:testid="):
        testid = selector[16:].strip("\"'")
        candidates.append(
            SelectorCandidate(
                strategy="testid",
                value=testid,
                confidence="high",
            )
        )
    elif selector.startswith("internal:attr="):
        # Attribute selector - treat as CSS
        attr_part = selector[14:]
        candidates.append(
            SelectorCandidate(
                strategy="css",
                value=f"[{attr_part}]",
                confidence="medium",
            )
        )
    else:
        # CSS fallback
        candidates.append(
            SelectorCandidate(
                strategy="css",
                value=selector,
                confidence="low",
            )
        )

    return candidates


def import_trace(trace_path: Path) -> RecordingSession:
    """Import a playwright-crx trace.zip into a RecordingSession.

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
    start_time: datetime | None = None
    source_url: str = ""

    with zipfile.ZipFile(trace_path) as z:
        # Parse trace.trace (NDJSON format)
        trace_data = z.read("trace.trace").decode("utf-8")

        for line in trace_data.splitlines():
            if not line.strip():
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # Skip malformed lines

            # Only process action events
            if entry.get("type") != "action":
                continue

            method = entry.get("method", "")
            class_name = entry.get("class", "")
            params = entry.get("params", {})

            # Skip non-user actions
            if class_name not in ("Locator", "Page", "Keyboard"):
                continue

            event_type = METHOD_MAP.get(method)
            if not event_type:
                continue

            # Parse timestamp (Playwright uses milliseconds)
            start_time_ms = entry.get("startTime", 0)
            timestamp = datetime.fromtimestamp(start_time_ms / 1000, tz=UTC)

            if start_time is None:
                start_time = timestamp

            # Extract URL from navigate events or page info
            if method == "goto":
                url = params.get("url", "")
                if not source_url:
                    source_url = url
            else:
                url = source_url  # Use last known URL

            # Parse selector
            selector = params.get("selector", "")
            selectors = parse_playwright_selector(selector)

            # Extract point coordinates
            point = entry.get("point", {})
            x = point.get("x") if point else None
            y = point.get("y") if point else None

            # Build UIEvent
            event = UIEvent(
                id=str(uuid4()),
                timestamp=timestamp,
                relative_time_ms=int((timestamp - start_time).total_seconds() * 1000),
                event_type=event_type,
                url=url,
                selectors=selectors,
                value=params.get("value"),
                key=params.get("key"),
                x=int(x) if x is not None else None,
                y=int(y) if y is not None else None,
            )
            events.append(event)

    # Create session
    session_id = f"sess_{uuid4().hex[:12]}"
    end_time = events[-1].timestamp if events else (start_time or datetime.now(tz=UTC))
    duration_ms = events[-1].relative_time_ms if events else 0

    return RecordingSession(
        metadata=SessionMetadata(
            id=session_id,
            version=1,
            started_at=start_time or datetime.now(tz=UTC),
            ended_at=end_time,
            duration_ms=duration_ms,
            source_url=source_url,
        ),
        events=events,
    )
