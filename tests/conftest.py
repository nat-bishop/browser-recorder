"""Shared pytest fixtures for browser-agents tests.

Fixtures here are automatically available to all test files.
See: https://docs.pytest.org/en/stable/reference/fixtures.html
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

if TYPE_CHECKING:
    from browser_agents.models import ActionDefinition, Recording


@pytest.fixture
def recordings_dir(tmp_path: Path) -> Path:
    """Temporary directory for test recordings.

    Uses pytest's tmp_path fixture which creates a unique temp dir per test.
    Automatically cleaned up after test completes.
    """
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    return recordings


@pytest.fixture
def sample_recording(recordings_dir: Path) -> Path:
    """Create a minimal valid recording for testing.

    Returns path to a JSONL file with:
    - Valid metadata header
    - One navigate event
    - One click event
    """
    recording = recordings_dir / "test_session.jsonl"
    recording.write_text(
        '{"session_id": "test123", "start_url": "https://example.com", "started_at": "2025-01-01T00:00:00+00:00"}\n'
        '{"timestamp": 1.0, "event_type": "navigate", "url": "https://example.com"}\n'
        '{"timestamp": 2.0, "event_type": "click", "selector": "#main-button", "x": 100, "y": 200}\n'
    )
    return recording


@pytest.fixture
def empty_recording(recordings_dir: Path) -> Path:
    """Create a recording with only metadata (no events)."""
    recording = recordings_dir / "empty_session.jsonl"
    recording.write_text(
        '{"session_id": "empty", "start_url": "https://example.com", "started_at": "2025-01-01T00:00:00+00:00"}\n'
    )
    return recording


@pytest.fixture
def invalid_recording(recordings_dir: Path) -> Path:
    """Create an invalid recording file for error testing."""
    recording = recordings_dir / "invalid.jsonl"
    recording.write_text("not valid json\n")
    return recording


# =============================================================================
# Phase 3: Converter test fixtures
# =============================================================================


@pytest.fixture
def sample_recording_model() -> "Recording":
    """Create a Recording model for converter tests."""
    from browser_agents.models import RecordedEvent, Recording

    return Recording(
        session_id="test123",
        start_url="https://example.com",
        started_at=datetime.now(UTC),
        events=[
            RecordedEvent(timestamp=1.0, event_type="navigate", url="https://example.com"),
            RecordedEvent(
                timestamp=2.0, event_type="type", selector="#email", value="test@example.com"
            ),
            RecordedEvent(timestamp=3.0, event_type="click", selector="#submit"),
        ],
    )


@pytest.fixture
def verbose_recording_model() -> "Recording":
    """Create a Recording with verbose keystroke events for preprocessing tests."""
    from browser_agents.models import RecordedEvent, Recording

    return Recording(
        session_id="verbose123",
        start_url="https://example.com",
        started_at=datetime.now(UTC),
        events=[
            RecordedEvent(timestamp=1.0, event_type="navigate", url="https://example.com"),
            # Keystroke sequence that should be collapsed
            RecordedEvent(timestamp=2.0, event_type="type", selector="#email", value="t"),
            RecordedEvent(timestamp=2.1, event_type="type", selector="#email", value="te"),
            RecordedEvent(timestamp=2.2, event_type="type", selector="#email", value="tes"),
            RecordedEvent(timestamp=2.3, event_type="type", selector="#email", value="test"),
            # Scroll events that should be removed
            RecordedEvent(timestamp=3.0, event_type="scroll", scroll_x=0, scroll_y=100),
            RecordedEvent(timestamp=3.1, event_type="scroll", scroll_x=0, scroll_y=200),
            # Click
            RecordedEvent(timestamp=4.0, event_type="click", selector="#submit", x=100, y=200),
            # Duplicate navigation that should be deduplicated
            RecordedEvent(timestamp=5.0, event_type="navigate", url="https://example.com/result"),
            RecordedEvent(timestamp=5.1, event_type="navigate", url="https://example.com/result"),
        ],
    )


@pytest.fixture
def mock_action_definition() -> "ActionDefinition":
    """Create a valid ActionDefinition for mocking LLM responses."""
    from browser_agents.models import ActionDefinition, ActionParameter, ActionStep

    return ActionDefinition(
        name="login_user",
        description="Log into the application with email and password",
        parameters=[
            ActionParameter(
                name="email",
                description="User email address",
                example="test@example.com",
            ),
        ],
        steps=[
            ActionStep(
                action="navigate",
                target="https://example.com",
                description="Go to example.com",
            ),
            ActionStep(
                action="type",
                target="#email",
                value="{email}",
                description="Enter email address",
            ),
            ActionStep(
                action="click",
                target="#submit",
                description="Click submit button",
            ),
        ],
        domains=["example.com"],
    )


@pytest.fixture
def mock_llm(mock_action_definition: "ActionDefinition") -> AsyncMock:
    """Create a mock LLM that returns a valid ActionDefinition.

    The mock chain simulates:
    get_structured_llm(ActionDefinition)  # returns mock_llm
        .with_retry(...)                   # returns same mock (sync method)
        .ainvoke(messages)                 # returns mock_action_definition
    """
    from unittest.mock import AsyncMock, Mock

    mock = Mock()  # Use regular Mock for the base
    mock.ainvoke = AsyncMock(return_value=mock_action_definition)
    # with_retry returns the same mock (it's a sync method that returns a Runnable)
    mock.with_retry.return_value = mock
    return mock
