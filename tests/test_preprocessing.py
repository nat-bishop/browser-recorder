"""Tests for event preprocessing in converter module.

These tests verify that verbose recordings are properly collapsed
before being sent to the LLM.
"""

from typing import TYPE_CHECKING

from browser_agents.converter import preprocess_events
from browser_agents.models import RecordedEvent

if TYPE_CHECKING:
    from browser_agents.models import Workflow


class TestPreprocessEvents:
    """Tests for preprocess_events function."""

    def test_collapses_consecutive_type_events(self) -> None:
        """Consecutive type events on same selector should be collapsed to final value."""
        events = [
            RecordedEvent(timestamp=1.0, event_type="type", selector="#email", value="t"),
            RecordedEvent(timestamp=1.1, event_type="type", selector="#email", value="te"),
            RecordedEvent(timestamp=1.2, event_type="type", selector="#email", value="tes"),
            RecordedEvent(timestamp=1.3, event_type="type", selector="#email", value="test"),
        ]

        result = preprocess_events(events)

        assert len(result) == 1
        assert result[0]["event_type"] == "type"
        assert result[0]["selector"] == "#email"
        assert result[0]["value"] == "test"

    def test_preserves_type_events_on_different_selectors(self) -> None:
        """Type events on different selectors should not be collapsed together."""
        events = [
            RecordedEvent(timestamp=1.0, event_type="type", selector="#email", value="user"),
            RecordedEvent(timestamp=2.0, event_type="type", selector="#password", value="pass"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert result[0]["value"] == "user"
        assert result[1]["value"] == "pass"

    def test_removes_scroll_events(self) -> None:
        """Scroll events should be filtered out."""
        events = [
            RecordedEvent(timestamp=1.0, event_type="click", selector="#btn"),
            RecordedEvent(timestamp=2.0, event_type="scroll", scroll_x=0, scroll_y=100),
            RecordedEvent(timestamp=3.0, event_type="scroll", scroll_x=0, scroll_y=200),
            RecordedEvent(timestamp=4.0, event_type="click", selector="#other"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert all(e["event_type"] == "click" for e in result)

    def test_deduplicates_consecutive_navigations(self) -> None:
        """Consecutive navigations to same URL should be deduplicated."""
        events = [
            RecordedEvent(timestamp=1.0, event_type="navigate", url="https://example.com"),
            RecordedEvent(timestamp=2.0, event_type="navigate", url="https://example.com"),
            RecordedEvent(timestamp=3.0, event_type="navigate", url="https://other.com"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert result[0]["url"] == "https://example.com"
        assert result[1]["url"] == "https://other.com"

    def test_strips_null_fields_and_timestamps(self) -> None:
        """Null fields and timestamps should not be in output."""
        events = [
            RecordedEvent(
                timestamp=123.456,
                event_type="click",
                selector="#btn",
                x=100,
                y=200,
                url=None,  # Should not appear in output
            ),
        ]

        result = preprocess_events(events)

        assert len(result) == 1
        assert "timestamp" not in result[0]
        assert "url" not in result[0]
        assert result[0]["x"] == 100

    def test_handles_empty_events(self) -> None:
        """Empty event list should return empty list."""
        result = preprocess_events([])
        assert result == []

    def test_flushes_pending_type_at_end(self) -> None:
        """Type events at end of recording should be included."""
        events = [
            RecordedEvent(timestamp=1.0, event_type="click", selector="#start"),
            RecordedEvent(timestamp=2.0, event_type="type", selector="#input", value="final"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert result[1]["value"] == "final"

    def test_preserves_click_coordinates(self) -> None:
        """Click events should preserve x, y coordinates."""
        events = [
            RecordedEvent(timestamp=1.0, event_type="click", selector="#btn", x=150, y=250),
        ]

        result = preprocess_events(events)

        assert result[0]["x"] == 150
        assert result[0]["y"] == 250

    def test_verbose_workflow_fixture(self, verbose_workflow_model: "Workflow") -> None:
        """Test with the verbose workflow fixture from conftest."""
        # 10 input events should collapse to fewer
        result = preprocess_events(verbose_workflow_model.events)

        # Should have: 1 navigate + 1 collapsed type + 1 click + 1 deduplicated navigate = 4
        assert len(result) == 4

        # Verify type was collapsed
        type_events = [e for e in result if e["event_type"] == "type"]
        assert len(type_events) == 1
        assert type_events[0]["value"] == "test"

        # Verify scroll was removed
        assert not any(e["event_type"] == "scroll" for e in result)
