"""Tests for event preprocessing in converter module.

These tests verify that UIEvents are properly preprocessed
before being sent to the LLM.
"""

from datetime import UTC, datetime

from browser_agents.converter import preprocess_events
from browser_agents.models import UIEvent, UIEventType


def make_event(
    event_type: str,
    selector: str | None = None,
    value: str | None = None,
    url: str | None = None,
    key: str | None = None,
    element_type: str | None = None,
    element_text: str | None = None,
    element_label: str | None = None,
    frame_type: str = "main",
) -> UIEvent:
    """Helper to create UIEvent for testing."""
    return UIEvent(
        id=f"evt_{id(event_type)}",
        timestamp=datetime.now(UTC),
        relative_time_ms=0,
        event_type=UIEventType(event_type),
        url=url or "https://example.com",
        selector=selector,
        value=value,
        key=key,
        element_type=element_type,
        element_text=element_text,
        element_label=element_label,
        frame_type=frame_type,
    )


class TestPreprocessEvents:
    """Tests for preprocess_events function."""

    def test_collapses_consecutive_type_events(self) -> None:
        """Consecutive type events on same selector should be collapsed to final value."""
        events = [
            make_event("type", "#email", value="t"),
            make_event("type", "#email", value="te"),
            make_event("type", "#email", value="tes"),
            make_event("type", "#email", value="test"),
        ]

        result = preprocess_events(events)

        assert len(result) == 1
        assert result[0]["event_type"] == "type"
        assert result[0]["selector"] == "#email"
        assert result[0]["value"] == "test"

    def test_preserves_type_events_on_different_selectors(self) -> None:
        """Type events on different selectors should not be collapsed together."""
        events = [
            make_event("type", "#email", value="user"),
            make_event("type", "#password", value="pass"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert result[0]["value"] == "user"
        assert result[1]["value"] == "pass"

    def test_removes_scroll_events(self) -> None:
        """Scroll events should be filtered out."""
        events = [
            make_event("click", "#btn"),
            make_event("scroll"),
            make_event("scroll"),
            make_event("click", "#other"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert all(e["event_type"] == "click" for e in result)

    def test_deduplicates_consecutive_navigations(self) -> None:
        """Consecutive navigations to same URL should be deduplicated."""
        events = [
            make_event("navigate", url="https://example.com"),
            make_event("navigate", url="https://example.com"),
            make_event("navigate", url="https://other.com"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert result[0]["url"] == "https://example.com"
        assert result[1]["url"] == "https://other.com"

    def test_handles_empty_events(self) -> None:
        """Empty event list should return empty list."""
        result = preprocess_events([])
        assert result == []

    def test_flushes_pending_type_at_end(self) -> None:
        """Type events at end of recording should be included."""
        events = [
            make_event("click", "#start"),
            make_event("type", "#input", value="final"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert result[1]["value"] == "final"

    def test_includes_element_context(self) -> None:
        """Element context should be included when available."""
        events = [
            make_event(
                "click",
                'role=button[name="Submit"]',
                element_type="button",
                element_text="Submit Form",
            ),
        ]

        result = preprocess_events(events)

        assert len(result) == 1
        assert result[0]["element_type"] == "button"
        assert result[0]["element_text"] == "Submit Form"

    def test_includes_key_for_keypress(self) -> None:
        """Key press events should include the key."""
        events = [
            make_event("key_press", key="Enter"),
        ]

        result = preprocess_events(events)

        assert len(result) == 1
        assert result[0]["event_type"] == "key_press"
        assert result[0]["key"] == "Enter"

    def test_iframe_context_included(self) -> None:
        """Iframe events should include frame context."""
        events = [
            make_event(
                "click",
                "#btn",
                frame_type="iframe",
            ),
        ]
        # Set frame_src after creation
        events[0].frame_src = "https://iframe.example.com"

        result = preprocess_events(events)

        assert result[0]["frame"] == "iframe"
        assert result[0]["frame_src"] == "https://iframe.example.com"

    def test_handles_all_event_types(self) -> None:
        """All 11 event types should be handled."""
        event_types = [
            "click",
            "double_click",
            "right_click",
            "type",
            "clear",
            "select_option",
            "check",
            "uncheck",
            "scroll",
            "navigate",
            "key_press",
        ]

        events = [make_event(t, "#el") for t in event_types]
        result = preprocess_events(events)

        # Scroll is filtered out
        assert len(result) == 10
        result_types = [e["event_type"] for e in result]
        assert "scroll" not in result_types
