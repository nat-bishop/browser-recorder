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
    from browser_agents.models import ActionDefinition, RecordingSession


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    """Temporary directory for test sessions.

    Uses pytest's tmp_path fixture which creates a unique temp dir per test.
    Automatically cleaned up after test completes.
    """
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    return sessions


@pytest.fixture
def sample_session(sessions_dir: Path) -> Path:
    """Create a minimal valid session for testing.

    Returns path to a session directory with:
    - Valid session metadata
    - One navigate event
    - One click event
    """
    from browser_agents.models import (
        RecordingSession,
        SessionMetadata,
        UIEvent,
        UIEventType,
    )

    session = RecordingSession(
        metadata=SessionMetadata(
            id="test123",
            version=1,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=1000,
            source_url="https://example.com",
            browser_name="Chrome",
            browser_version="120.0.0.0",
            viewport_width=1920,
            viewport_height=1080,
        ),
        events=[
            UIEvent(
                id="evt1",
                timestamp=datetime.now(UTC),
                relative_time_ms=0,
                event_type=UIEventType.NAVIGATE,
                url="https://example.com",
            ),
            UIEvent(
                id="evt2",
                timestamp=datetime.now(UTC),
                relative_time_ms=1000,
                event_type=UIEventType.CLICK,
                url="https://example.com",
                selector='role=button[name="Submit"]',
            ),
        ],
    )

    session_dir = sessions_dir / "test123"
    session_dir.mkdir()
    session_file = session_dir / "session.json"
    session_file.write_text(session.model_dump_json(indent=2))
    return session_dir


@pytest.fixture
def sample_session_file(sample_session: Path) -> Path:
    """Return the session.json file path from sample_session."""
    return sample_session / "session.json"


@pytest.fixture
def empty_session(sessions_dir: Path) -> Path:
    """Create a session with no events."""
    from browser_agents.models import RecordingSession, SessionMetadata

    session = RecordingSession(
        metadata=SessionMetadata(
            id="empty",
            version=1,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=0,
            source_url="https://example.com",
            browser_name="Chrome",
            browser_version="120.0.0.0",
            viewport_width=1920,
            viewport_height=1080,
        ),
        events=[],
    )

    session_dir = sessions_dir / "empty"
    session_dir.mkdir()
    session_file = session_dir / "session.json"
    session_file.write_text(session.model_dump_json(indent=2))
    return session_dir


@pytest.fixture
def invalid_session(sessions_dir: Path) -> Path:
    """Create an invalid session file for error testing."""
    session_dir = sessions_dir / "invalid"
    session_dir.mkdir()
    session_file = session_dir / "session.json"
    session_file.write_text("not valid json\n")
    return session_dir


# =============================================================================
# Converter test fixtures
# =============================================================================


@pytest.fixture
def sample_session_model() -> "RecordingSession":
    """Create a RecordingSession model for converter tests."""
    from browser_agents.models import (
        RecordingSession,
        SessionMetadata,
        UIEvent,
        UIEventType,
    )

    return RecordingSession(
        metadata=SessionMetadata(
            id="test123",
            version=1,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=3000,
            source_url="https://example.com",
            browser_name="Chrome",
            browser_version="120.0.0.0",
            viewport_width=1920,
            viewport_height=1080,
        ),
        events=[
            UIEvent(
                id="evt1",
                timestamp=datetime.now(UTC),
                relative_time_ms=0,
                event_type=UIEventType.NAVIGATE,
                url="https://example.com",
            ),
            UIEvent(
                id="evt2",
                timestamp=datetime.now(UTC),
                relative_time_ms=1000,
                event_type=UIEventType.TYPE,
                url="https://example.com",
                selector='role=textbox[name="Email"]',
                value="test@example.com",
            ),
            UIEvent(
                id="evt3",
                timestamp=datetime.now(UTC),
                relative_time_ms=2000,
                event_type=UIEventType.CLICK,
                url="https://example.com",
                selector='role=button[name="Submit"]',
            ),
        ],
    )


@pytest.fixture
def mock_action_definition() -> "ActionDefinition":
    """Create a valid ActionDefinition for mocking LLM responses."""
    from browser_agents.models import (
        ActionDefinition,
        ActionParameter,
        ActionStep,
        StepAction,
    )

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
                action=StepAction.navigate,
                target="https://example.com",
                description="Go to example.com",
            ),
            ActionStep(
                action=StepAction.type,
                target='role=textbox[name="Email"]',
                value="{email}",
                description="Enter email address",
            ),
            ActionStep(
                action=StepAction.click,
                target='role=button[name="Submit"]',
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
