"""Unit tests for Pydantic models.

These tests are fast and don't require a browser.
Run with: uv run pytest tests/test_models.py -v
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from browser_agents.models import (
    ActionDefinition,
    ActionParameter,
    ActionStep,
    RecordingSession,
    SelectorCandidate,
    SessionMetadata,
    StepAction,
    UIEvent,
    UIEventType,
)


class TestSelectorCandidate:
    """Tests for SelectorCandidate model."""

    def test_role_selector(self) -> None:
        """Role selector with name is valid."""
        selector = SelectorCandidate(
            strategy="role",
            value='role=button[name="Submit"]',
            confidence="high",
            role="button",
            name="Submit",
        )
        assert selector.strategy == "role"
        assert selector.role == "button"
        assert selector.name == "Submit"
        assert selector.confidence == "high"

    def test_label_selector(self) -> None:
        """Label selector is valid."""
        selector = SelectorCandidate(
            strategy="label",
            value="Email",
            confidence="high",
        )
        assert selector.strategy == "label"
        assert selector.value == "Email"

    def test_css_selector(self) -> None:
        """CSS selector (fallback) is valid."""
        selector = SelectorCandidate(
            strategy="css",
            value="#submit-btn",
            confidence="low",
        )
        assert selector.strategy == "css"
        assert selector.confidence == "low"

    @pytest.mark.parametrize(
        "strategy", ["role", "label", "placeholder", "text", "testid", "css"]
    )
    def test_all_valid_strategies(self, strategy: str) -> None:
        """All defined selector strategies are accepted."""
        selector = SelectorCandidate(
            strategy=strategy,  # type: ignore[arg-type]
            value="test",
            confidence="medium",
        )
        assert selector.strategy == strategy

    def test_invalid_strategy_rejected(self) -> None:
        """Invalid strategy raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SelectorCandidate(
                strategy="invalid",  # type: ignore[arg-type]
                value="test",
                confidence="medium",
            )
        assert "strategy" in str(exc_info.value)

    def test_serialization_roundtrip(self) -> None:
        """SelectorCandidate can be serialized to JSON and back."""
        original = SelectorCandidate(
            strategy="role",
            value='role=button[name="Submit"]',
            confidence="high",
            role="button",
            name="Submit",
        )
        json_str = original.model_dump_json()
        restored = SelectorCandidate.model_validate_json(json_str)
        assert restored == original


class TestUIEventType:
    """Tests for UIEventType enum."""

    def test_all_event_types_exist(self) -> None:
        """All expected event types are defined."""
        assert UIEventType.CLICK == "click"
        assert UIEventType.DOUBLE_CLICK == "double_click"
        assert UIEventType.RIGHT_CLICK == "right_click"
        assert UIEventType.TYPE == "type"
        assert UIEventType.CLEAR == "clear"
        assert UIEventType.SELECT_OPTION == "select_option"
        assert UIEventType.CHECK == "check"
        assert UIEventType.UNCHECK == "uncheck"
        assert UIEventType.SCROLL == "scroll"
        assert UIEventType.NAVIGATE == "navigate"
        assert UIEventType.KEY_PRESS == "key_press"

    def test_event_type_is_string_enum(self) -> None:
        """UIEventType values can be used as strings."""
        assert UIEventType.CLICK.value == "click"


class TestUIEvent:
    """Tests for UIEvent model."""

    def test_click_event_with_selectors(self) -> None:
        """Click event with multiple selectors is valid."""
        event = UIEvent(
            id="evt_001",
            timestamp=datetime.now(UTC),
            relative_time_ms=1000,
            event_type=UIEventType.CLICK,
            url="https://example.com",
            selectors=[
                SelectorCandidate(
                    strategy="role",
                    value="button",
                    confidence="high",
                    role="button",
                    name="Submit",
                ),
                SelectorCandidate(
                    strategy="testid", value="submit-btn", confidence="high"
                ),
                SelectorCandidate(strategy="css", value="#submit", confidence="low"),
            ],
            element_type="button",
            element_text="Submit",
            x=100,
            y=200,
        )
        assert event.event_type == UIEventType.CLICK
        assert len(event.selectors) == 3
        assert event.selectors[0].strategy == "role"
        assert event.x == 100
        assert event.y == 200

    def test_type_event(self) -> None:
        """Type event with value is valid."""
        event = UIEvent(
            id="evt_002",
            timestamp=datetime.now(UTC),
            relative_time_ms=2000,
            event_type=UIEventType.TYPE,
            url="https://example.com",
            selectors=[
                SelectorCandidate(strategy="label", value="Email", confidence="high")
            ],
            element_type="input",
            input_type="email",
            placeholder="Enter your email",
            value="test@example.com",
        )
        assert event.event_type == UIEventType.TYPE
        assert event.value == "test@example.com"
        assert event.input_type == "email"

    def test_navigate_event(self) -> None:
        """Navigate event is valid."""
        event = UIEvent(
            id="evt_003",
            timestamp=datetime.now(UTC),
            relative_time_ms=0,
            event_type=UIEventType.NAVIGATE,
            url="https://example.com/page",
            selectors=[],
        )
        assert event.event_type == UIEventType.NAVIGATE
        assert event.url == "https://example.com/page"

    def test_scroll_event(self) -> None:
        """Scroll event with coordinates is valid."""
        event = UIEvent(
            id="evt_004",
            timestamp=datetime.now(UTC),
            relative_time_ms=3000,
            event_type=UIEventType.SCROLL,
            url="https://example.com",
            selectors=[],
            scroll_x=0,
            scroll_y=500,
        )
        assert event.scroll_y == 500

    def test_key_press_event(self) -> None:
        """Key press event is valid."""
        event = UIEvent(
            id="evt_005",
            timestamp=datetime.now(UTC),
            relative_time_ms=4000,
            event_type=UIEventType.KEY_PRESS,
            url="https://example.com",
            selectors=[],
            key="Enter",
        )
        assert event.event_type == UIEventType.KEY_PRESS
        assert event.key == "Enter"

    def test_iframe_event(self) -> None:
        """Event in iframe captures frame context."""
        event = UIEvent(
            id="evt_006",
            timestamp=datetime.now(UTC),
            relative_time_ms=5000,
            event_type=UIEventType.CLICK,
            url="https://example.com",
            selectors=[],
            frame_type="iframe",
            frame_src="https://iframe.example.com/content",
        )
        assert event.frame_type == "iframe"
        assert event.frame_src == "https://iframe.example.com/content"

    def test_default_frame_type_is_main(self) -> None:
        """Default frame_type is main."""
        event = UIEvent(
            id="evt_007",
            timestamp=datetime.now(UTC),
            relative_time_ms=0,
            event_type=UIEventType.CLICK,
            url="https://example.com",
            selectors=[],
        )
        assert event.frame_type == "main"

    def test_missing_required_fields_rejected(self) -> None:
        """Missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            UIEvent(  # type: ignore[call-arg]
                event_type=UIEventType.CLICK,
            )

    def test_serialization_roundtrip(self) -> None:
        """UIEvent can be serialized to JSON and back."""
        original = UIEvent(
            id="evt_001",
            timestamp=datetime.now(UTC),
            relative_time_ms=1000,
            event_type=UIEventType.CLICK,
            url="https://example.com",
            selectors=[
                SelectorCandidate(
                    strategy="role",
                    value="button",
                    confidence="high",
                    role="button",
                    name="Submit",
                ),
            ],
            element_type="button",
            x=100,
            y=200,
        )
        json_str = original.model_dump_json()
        restored = UIEvent.model_validate_json(json_str)
        assert restored.id == original.id
        assert restored.event_type == original.event_type
        assert len(restored.selectors) == 1


class TestSessionMetadata:
    """Tests for SessionMetadata model."""

    def test_minimal_metadata(self) -> None:
        """Minimal metadata is valid."""
        metadata = SessionMetadata(
            id="sess_001",
            started_at=datetime.now(UTC),
            source_url="https://example.com",
        )
        assert metadata.id == "sess_001"
        assert metadata.version == 1
        assert metadata.ended_at is None

    def test_full_metadata(self) -> None:
        """Full metadata with all fields is valid."""
        metadata = SessionMetadata(
            id="sess_002",
            version=1,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=30000,
            source_url="https://example.com",
            browser_name="Chrome",
            browser_version="120.0.0",
            viewport_width=1920,
            viewport_height=1080,
            name="Login test",
            description="Test the login flow",
        )
        assert metadata.browser_name == "Chrome"
        assert metadata.viewport_width == 1920


class TestRecordingSession:
    """Tests for RecordingSession model."""

    def test_session_with_events(self) -> None:
        """Session with events is valid."""
        session = RecordingSession(
            metadata=SessionMetadata(
                id="sess_001",
                started_at=datetime.now(UTC),
                source_url="https://example.com",
            ),
            events=[
                UIEvent(
                    id="evt_001",
                    timestamp=datetime.now(UTC),
                    relative_time_ms=0,
                    event_type=UIEventType.NAVIGATE,
                    url="https://example.com",
                    selectors=[],
                ),
                UIEvent(
                    id="evt_002",
                    timestamp=datetime.now(UTC),
                    relative_time_ms=1000,
                    event_type=UIEventType.CLICK,
                    url="https://example.com",
                    selectors=[
                        SelectorCandidate(
                            strategy="css", value="#btn", confidence="low"
                        )
                    ],
                ),
            ],
        )
        assert session.metadata.id == "sess_001"
        assert len(session.events) == 2

    def test_session_empty_events(self) -> None:
        """Session with no events is valid."""
        session = RecordingSession(
            metadata=SessionMetadata(
                id="sess_empty",
                started_at=datetime.now(UTC),
                source_url="https://example.com",
            ),
            events=[],
        )
        assert len(session.events) == 0

    def test_session_default_events(self) -> None:
        """Events list defaults to empty."""
        session = RecordingSession(
            metadata=SessionMetadata(
                id="sess_default",
                started_at=datetime.now(UTC),
                source_url="https://example.com",
            ),
        )
        assert session.events == []

    def test_serialization_roundtrip(self) -> None:
        """RecordingSession can be serialized to JSON and back."""
        original = RecordingSession(
            metadata=SessionMetadata(
                id="sess_roundtrip",
                started_at=datetime.now(UTC),
                source_url="https://example.com",
            ),
            events=[
                UIEvent(
                    id="evt_001",
                    timestamp=datetime.now(UTC),
                    relative_time_ms=0,
                    event_type=UIEventType.NAVIGATE,
                    url="https://example.com",
                    selectors=[],
                ),
            ],
        )
        json_str = original.model_dump_json()
        restored = RecordingSession.model_validate_json(json_str)
        assert restored.metadata.id == original.metadata.id
        assert len(restored.events) == 1


class TestStepAction:
    """Tests for StepAction enum."""

    def test_all_action_types_exist(self) -> None:
        """All expected action types are defined."""
        assert StepAction.navigate == "navigate"
        assert StepAction.click == "click"
        assert StepAction.type == "type"
        assert StepAction.select == "select"
        assert StepAction.scroll == "scroll"
        assert StepAction.wait == "wait"

    def test_step_action_is_string_enum(self) -> None:
        """StepAction values can be used as strings."""
        assert StepAction.click.value == "click"


class TestActionStep:
    """Tests for ActionStep model."""

    def test_action_step_with_selector(self) -> None:
        """ActionStep with target selector is valid."""
        step = ActionStep(
            action=StepAction.click,
            target="#submit-btn",
            description="Click the submit button",
        )
        assert step.action == StepAction.click
        assert step.target == "#submit-btn"

    def test_action_step_with_value_placeholder(self) -> None:
        """ActionStep with parameter placeholder is valid."""
        step = ActionStep(
            action=StepAction.type,
            target="#email",
            value="{email}",
            description="Enter email address",
        )
        assert step.value == "{email}"

    def test_action_step_with_fallback_coords(self) -> None:
        """ActionStep with fallback coordinates is valid."""
        step = ActionStep(
            action=StepAction.click,
            target="#btn",
            fallback_coords=[100, 200],
            fallback_text="Submit",
            description="Click submit",
        )
        assert step.fallback_coords == [100, 200]
        assert step.fallback_text == "Submit"

    def test_action_step_serialization_roundtrip(self) -> None:
        """ActionStep can be serialized to JSON and back."""
        original = ActionStep(
            action=StepAction.click,
            target="#btn",
            fallback_coords=[50, 75],
            description="Click button",
        )
        json_str = original.model_dump_json()
        restored = ActionStep.model_validate_json(json_str)
        assert restored == original
        assert restored.fallback_coords == [50, 75]


class TestActionDefinition:
    """Tests for ActionDefinition model."""

    def test_action_definition(self) -> None:
        """ActionDefinition with steps is valid."""
        action = ActionDefinition(
            name="login",
            description="Log into the site",
            parameters=[
                ActionParameter(
                    name="email", description="Email", example="test@example.com"
                ),
                ActionParameter(
                    name="password",
                    description="Password",
                    example="secret123",
                    is_sensitive=True,
                ),
            ],
            steps=[
                ActionStep(
                    action=StepAction.type,
                    target="#email",
                    value="{email}",
                    description="Enter email",
                ),
                ActionStep(
                    action=StepAction.type,
                    target="#password",
                    value="{password}",
                    description="Enter password",
                ),
                ActionStep(
                    action=StepAction.click,
                    target="#login-btn",
                    description="Click login",
                ),
            ],
            domains=["example.com"],
        )
        assert action.name == "login"
        assert len(action.parameters) == 2
        assert action.parameters[1].is_sensitive is True
        assert len(action.steps) == 3

    def test_action_definition_serialization_roundtrip(self) -> None:
        """ActionDefinition can be serialized to JSON and back."""
        original = ActionDefinition(
            name="test",
            description="Test action",
            parameters=[],
            steps=[
                ActionStep(action=StepAction.click, target="#btn", description="Click")
            ],
            domains=["example.com"],
        )
        json_str = original.model_dump_json()
        restored = ActionDefinition.model_validate_json(json_str)
        assert restored.name == original.name
