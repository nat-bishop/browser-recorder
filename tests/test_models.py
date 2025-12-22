"""Unit tests for Pydantic models.

These tests are fast and don't require a browser.
Run with: uv run pytest tests/test_models.py -v
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from browser_agents.models import (
    RecordedEvent,
    Recording,
)


class TestRecordedEvent:
    """Tests for RecordedEvent model."""

    def test_click_event_with_selector(self) -> None:
        """Click event with CSS selector is valid."""
        event = RecordedEvent(
            timestamp=1.0,
            event_type="click",
            selector="#submit-button",
            x=100,
            y=200,
        )
        assert event.event_type == "click"
        assert event.selector == "#submit-button"
        assert event.x == 100
        assert event.y == 200

    def test_click_event_coordinates_only(self) -> None:
        """Click event with only coordinates (no selector) is valid."""
        event = RecordedEvent(
            timestamp=1.0,
            event_type="click",
            x=50,
            y=75,
        )
        assert event.selector is None
        assert event.x == 50

    def test_type_event(self) -> None:
        """Type event with value is valid."""
        event = RecordedEvent(
            timestamp=1.0,
            event_type="type",
            value="hello world",
        )
        assert event.event_type == "type"
        assert event.value == "hello world"

    def test_navigate_event(self) -> None:
        """Navigate event with URL is valid."""
        event = RecordedEvent(
            timestamp=1.0,
            event_type="navigate",
            url="https://example.com/page",
        )
        assert event.event_type == "navigate"
        assert event.url == "https://example.com/page"

    def test_scroll_event(self) -> None:
        """Scroll event with coordinates is valid."""
        event = RecordedEvent(
            timestamp=1.0,
            event_type="scroll",
            scroll_x=0,
            scroll_y=500,
        )
        assert event.scroll_y == 500

    def test_wait_event(self) -> None:
        """Wait event (minimal fields) is valid."""
        event = RecordedEvent(
            timestamp=1.0,
            event_type="wait",
        )
        assert event.event_type == "wait"

    @pytest.mark.parametrize("event_type", ["click", "type", "navigate", "scroll", "wait"])
    def test_all_valid_event_types(self, event_type: str) -> None:
        """All defined event types are accepted."""
        event = RecordedEvent(timestamp=1.0, event_type=event_type)
        assert event.event_type == event_type

    def test_invalid_event_type_rejected(self) -> None:
        """Invalid event types raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RecordedEvent(timestamp=1.0, event_type="invalid_type")
        assert "event_type" in str(exc_info.value)

    def test_missing_timestamp_rejected(self) -> None:
        """Timestamp is required."""
        with pytest.raises(ValidationError):
            RecordedEvent(event_type="click")  # type: ignore[call-arg]

    def test_serialization_roundtrip(self) -> None:
        """Event can be serialized to JSON and back."""
        original = RecordedEvent(
            timestamp=1234567890.123,
            event_type="click",
            selector="button.primary",
            x=100,
            y=200,
        )
        json_str = original.model_dump_json()
        restored = RecordedEvent.model_validate_json(json_str)
        assert restored == original


class TestRecording:
    """Tests for Recording model."""

    def test_recording_with_events(self) -> None:
        """Recording with multiple events is valid."""
        recording = Recording(
            session_id="abc123",
            start_url="https://example.com",
            started_at=datetime.now(UTC),
            events=[
                RecordedEvent(timestamp=1.0, event_type="navigate", url="https://example.com"),
                RecordedEvent(timestamp=2.0, event_type="click", selector="#btn"),
            ],
        )
        assert recording.session_id == "abc123"
        assert len(recording.events) == 2

    def test_recording_empty_events(self) -> None:
        """Recording with no events is valid."""
        recording = Recording(
            session_id="empty",
            start_url="https://example.com",
            started_at=datetime.now(UTC),
            events=[],
        )
        assert len(recording.events) == 0

    def test_recording_default_events(self) -> None:
        """Events list defaults to empty."""
        recording = Recording(
            session_id="test",
            start_url="https://example.com",
            started_at=datetime.now(UTC),
        )
        assert recording.events == []


class TestStepAction:
    """Tests for StepAction enum."""

    def test_all_action_types_exist(self) -> None:
        """All expected action types are defined."""
        from browser_agents.models import StepAction

        assert StepAction.navigate == "navigate"
        assert StepAction.click == "click"
        assert StepAction.type == "type"
        assert StepAction.select == "select"
        assert StepAction.scroll == "scroll"
        assert StepAction.wait == "wait"

    def test_step_action_is_string_enum(self) -> None:
        """StepAction values can be used as strings."""
        from browser_agents.models import StepAction

        assert str(StepAction.click) == "StepAction.click"
        assert StepAction.click.value == "click"


class TestActionStep:
    """Tests for ActionStep model."""

    def test_action_step_with_selector(self) -> None:
        """ActionStep with target selector is valid."""
        from browser_agents.models import ActionStep, StepAction

        step = ActionStep(
            action=StepAction.click,
            target="#submit-btn",
            description="Click the submit button",
        )
        assert step.action == StepAction.click
        assert step.target == "#submit-btn"

    def test_action_step_with_value_placeholder(self) -> None:
        """ActionStep with parameter placeholder is valid."""
        from browser_agents.models import ActionStep, StepAction

        step = ActionStep(
            action=StepAction.type,
            target="#email",
            value="{email}",
            description="Enter email address",
        )
        assert step.value == "{email}"

    def test_action_step_with_fallback_coords(self) -> None:
        """ActionStep with fallback coordinates is valid."""
        from browser_agents.models import ActionStep, StepAction

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
        from browser_agents.models import ActionStep, StepAction

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


class TestWorkflow:
    """Tests for Workflow model."""

    def test_workflow_with_events(self) -> None:
        """Workflow with events is valid."""
        from browser_agents.models import RecordedEvent, Workflow

        workflow = Workflow(
            id="abc123",
            source_url="https://example.com",
            created_at=datetime.now(UTC),
            events=[
                RecordedEvent(timestamp=1.0, event_type="navigate", url="https://example.com"),
                RecordedEvent(timestamp=2.0, event_type="click", selector="#btn"),
            ],
        )
        assert workflow.id == "abc123"
        assert len(workflow.events) == 2
        assert workflow.actions == []
        assert workflow.media is None

    def test_workflow_with_action(self) -> None:
        """Workflow with action definition is valid."""
        from browser_agents.models import (
            ActionDefinition,
            ActionParameter,
            ActionStep,
            RecordedEvent,
            StepAction,
            Workflow,
        )

        action = ActionDefinition(
            name="login",
            description="Log into the site",
            parameters=[
                ActionParameter(name="email", description="Email", example="test@example.com")
            ],
            steps=[ActionStep(action=StepAction.click, target="#btn", description="Click")],
            domains=["example.com"],
        )

        workflow = Workflow(
            id="test123",
            source_url="https://example.com",
            created_at=datetime.now(UTC),
            events=[RecordedEvent(timestamp=1.0, event_type="click", selector="#btn")],
            actions=[action],
        )
        assert len(workflow.actions) == 1
        assert workflow.actions[0].name == "login"

    def test_workflow_with_legacy_action_field(self) -> None:
        """Workflow accepts legacy 'action' field and converts to 'actions'."""
        from browser_agents.models import (
            ActionDefinition,
            ActionStep,
            RecordedEvent,
            StepAction,
            Workflow,
        )

        action = ActionDefinition(
            name="legacy_action",
            description="Test legacy support",
            parameters=[],
            steps=[ActionStep(action=StepAction.click, target="#btn", description="Click")],
            domains=["example.com"],
        )

        # Pass singular 'action' field (legacy)
        workflow = Workflow(
            id="legacy123",
            source_url="https://example.com",
            created_at=datetime.now(UTC),
            events=[RecordedEvent(timestamp=1.0, event_type="click", selector="#btn")],
            action=action,
        )
        # Should be converted to 'actions' list
        assert len(workflow.actions) == 1
        assert workflow.actions[0].name == "legacy_action"

    def test_workflow_with_media_refs(self) -> None:
        """Workflow with media references is valid."""
        from browser_agents.models import MediaRefs, Workflow

        media = MediaRefs(video="recording.webm", audio="audio.mp3")

        workflow = Workflow(
            id="media123",
            source_url="https://example.com",
            created_at=datetime.now(UTC),
            events=[],
            media=media,
        )
        assert workflow.media is not None
        assert workflow.media.video == "recording.webm"

    def test_workflow_serialization_roundtrip(self) -> None:
        """Workflow can be serialized to JSON and back."""
        from browser_agents.models import RecordedEvent, Workflow

        original = Workflow(
            id="roundtrip",
            source_url="https://example.com",
            created_at=datetime.now(UTC),
            events=[
                RecordedEvent(timestamp=1.0, event_type="navigate", url="https://example.com"),
            ],
        )
        json_str = original.model_dump_json()
        restored = Workflow.model_validate_json(json_str)
        assert restored.id == original.id
        assert restored.source_url == original.source_url
        assert len(restored.events) == 1

    def test_workflow_version_defaults_to_2(self) -> None:
        """Workflow version defaults to 2 (with name, description, actions list)."""
        from browser_agents.models import Workflow

        workflow = Workflow(
            id="test",
            source_url="https://example.com",
            created_at=datetime.now(UTC),
            events=[],
        )
        assert workflow.version == 2
        assert workflow.name is None
        assert workflow.description is None
        assert workflow.actions == []


class TestErrorDiagnosis:
    """Tests for ErrorDiagnosis model."""

    def test_error_diagnosis_conversion_type(self) -> None:
        """ErrorDiagnosis with conversion error type is valid."""
        from browser_agents.models import ErrorDiagnosis

        diagnosis = ErrorDiagnosis(
            error_type="conversion",
            explanation="Tried to type into a dropdown element",
            suggestion="Delete this step or re-record",
            likely_cause="LLM generated wrong action type",
        )
        assert diagnosis.error_type == "conversion"

    def test_error_diagnosis_execution_type(self) -> None:
        """ErrorDiagnosis with execution error type is valid."""
        from browser_agents.models import ErrorDiagnosis

        diagnosis = ErrorDiagnosis(
            error_type="execution",
            explanation="Element not found",
            suggestion="Retry or check if selector changed",
            likely_cause="Selector may have changed since recording",
        )
        assert diagnosis.error_type == "execution"

    def test_error_diagnosis_verification_type(self) -> None:
        """ErrorDiagnosis with verification error type is valid."""
        from browser_agents.models import ErrorDiagnosis

        diagnosis = ErrorDiagnosis(
            error_type="verification",
            explanation="Form validation failed",
            suggestion="Check the input values",
            likely_cause="Invalid data entered",
        )
        assert diagnosis.error_type == "verification"

    def test_error_diagnosis_invalid_type_rejected(self) -> None:
        """ErrorDiagnosis rejects invalid error types."""
        from browser_agents.models import ErrorDiagnosis

        with pytest.raises(ValidationError):
            ErrorDiagnosis(
                error_type="unknown",  # type: ignore[arg-type]
                explanation="Test",
                suggestion="Test",
                likely_cause="Test",
            )

    def test_error_diagnosis_serialization_roundtrip(self) -> None:
        """ErrorDiagnosis can be serialized to JSON and back."""
        from browser_agents.models import ErrorDiagnosis

        original = ErrorDiagnosis(
            error_type="execution",
            explanation="Element not found on page",
            suggestion="Check if selector changed since recording",
            likely_cause="Selector may have changed due to dynamic content",
        )
        json_str = original.model_dump_json()
        restored = ErrorDiagnosis.model_validate_json(json_str)
        assert restored == original
        assert restored.error_type == "execution"
