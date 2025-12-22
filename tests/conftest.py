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
    from browser_agents.models import ActionDefinition, Workflow


@pytest.fixture
def workflows_dir(tmp_path: Path) -> Path:
    """Temporary directory for test workflows.

    Uses pytest's tmp_path fixture which creates a unique temp dir per test.
    Automatically cleaned up after test completes.
    """
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    return workflows


@pytest.fixture
def sample_workflow(workflows_dir: Path) -> Path:
    """Create a minimal valid workflow for testing.

    Returns path to a JSON file with:
    - Valid workflow metadata
    - One navigate event
    - One click event
    """
    from browser_agents.models import RecordedEvent, Workflow

    workflow = Workflow(
        id="test123",
        source_url="https://example.com",
        created_at=datetime.now(UTC),
        events=[
            RecordedEvent(timestamp=1.0, event_type="navigate", url="https://example.com"),
            RecordedEvent(timestamp=2.0, event_type="click", selector="#main-button", x=100, y=200),
        ],
    )

    workflow_file = workflows_dir / "test_session.json"
    workflow_file.write_text(workflow.model_dump_json(indent=2))
    return workflow_file


@pytest.fixture
def empty_workflow(workflows_dir: Path) -> Path:
    """Create a workflow with no events."""
    from browser_agents.models import Workflow

    workflow = Workflow(
        id="empty",
        source_url="https://example.com",
        created_at=datetime.now(UTC),
        events=[],
    )

    workflow_file = workflows_dir / "empty_session.json"
    workflow_file.write_text(workflow.model_dump_json(indent=2))
    return workflow_file


@pytest.fixture
def invalid_workflow(workflows_dir: Path) -> Path:
    """Create an invalid workflow file for error testing."""
    workflow_file = workflows_dir / "invalid.json"
    workflow_file.write_text("not valid json\n")
    return workflow_file


# =============================================================================
# Phase 3: Converter test fixtures
# =============================================================================


@pytest.fixture
def sample_workflow_model() -> "Workflow":
    """Create a Workflow model for converter tests."""
    from browser_agents.models import RecordedEvent, Workflow

    return Workflow(
        id="test123",
        source_url="https://example.com",
        created_at=datetime.now(UTC),
        events=[
            RecordedEvent(timestamp=1.0, event_type="navigate", url="https://example.com"),
            RecordedEvent(
                timestamp=2.0, event_type="type", selector="#email", value="test@example.com"
            ),
            RecordedEvent(timestamp=3.0, event_type="click", selector="#submit"),
        ],
    )


@pytest.fixture
def verbose_workflow_model() -> "Workflow":
    """Create a Workflow with verbose keystroke events for preprocessing tests."""
    from browser_agents.models import RecordedEvent, Workflow

    return Workflow(
        id="verbose123",
        source_url="https://example.com",
        created_at=datetime.now(UTC),
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
    from browser_agents.models import ActionDefinition, ActionParameter, ActionStep, StepAction

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
                target="#email",
                value="{email}",
                description="Enter email address",
            ),
            ActionStep(
                action=StepAction.click,
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
