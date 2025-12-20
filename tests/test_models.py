"""Unit tests for Pydantic models.

These tests are fast and don't require a browser.
Run with: uv run pytest tests/test_models.py -v
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from browser_agents.models import RecordedEvent, Recording


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
