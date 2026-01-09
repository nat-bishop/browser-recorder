"""Tests for event preprocessing in converter module.

These tests verify that UIEvents are properly preprocessed
before being sent to the LLM.
"""

from datetime import UTC, datetime

from browser_agents.converter import get_best_selector, preprocess_events
from browser_agents.models import SelectorCandidate, UIEvent, UIEventType


def make_event(
    event_type: str,
    selectors: list[SelectorCandidate] | None = None,
    value: str | None = None,
    url: str | None = None,
    key: str | None = None,
    element_type: str | None = None,
    element_text: str | None = None,
    element_label: str | None = None,
    x: int | None = None,
    y: int | None = None,
    frame_type: str = "main",
) -> UIEvent:
    """Helper to create UIEvent for testing."""
    return UIEvent(
        id=f"evt_{id(event_type)}",
        timestamp=datetime.now(UTC),
        relative_time_ms=0,
        event_type=UIEventType(event_type),
        url=url or "https://example.com",
        selectors=selectors or [],
        value=value,
        key=key,
        element_type=element_type,
        element_text=element_text,
        element_label=element_label,
        x=x,
        y=y,
        frame_type=frame_type,
    )


def css_selector(value: str) -> SelectorCandidate:
    """Helper to create CSS selector."""
    return SelectorCandidate(strategy="css", value=value, confidence="low")


def role_selector(role: str, name: str) -> SelectorCandidate:
    """Helper to create role selector."""
    return SelectorCandidate(
        strategy="role",
        value=f'role={role}[name="{name}"]',
        confidence="high",
        role=role,
        name=name,
    )


class TestGetBestSelector:
    """Tests for get_best_selector function."""

    def test_role_selector_preferred(self) -> None:
        """Role selector should be preferred over CSS."""
        selectors = [
            css_selector("#btn"),
            role_selector("button", "Submit"),
        ]
        result = get_best_selector(selectors)
        assert result == 'role=button[name="Submit"]'

    def test_high_confidence_preferred_within_same_priority(self) -> None:
        """High confidence selectors should be preferred within same strategy."""
        selectors = [
            SelectorCandidate(strategy="css", value="#low-conf", confidence="low"),
            SelectorCandidate(strategy="css", value="#high-conf", confidence="high"),
        ]
        result = get_best_selector(selectors)
        assert result == "#high-conf"

    def test_empty_list_returns_none(self) -> None:
        """Empty selector list should return None."""
        result = get_best_selector([])
        assert result is None

    def test_priority_order(self) -> None:
        """Selectors should follow priority: role > label > placeholder > text > testid > css."""
        selectors = [
            SelectorCandidate(strategy="css", value="#id", confidence="low"),
            SelectorCandidate(strategy="testid", value="test-id", confidence="high"),
            SelectorCandidate(strategy="text", value="Click", confidence="medium"),
            SelectorCandidate(
                strategy="placeholder", value="Enter", confidence="medium"
            ),
            SelectorCandidate(strategy="label", value="Email", confidence="high"),
            role_selector("button", "Submit"),
        ]
        result = get_best_selector(selectors)
        assert result == 'role=button[name="Submit"]'


class TestPreprocessEvents:
    """Tests for preprocess_events function."""

    def test_collapses_consecutive_type_events(self) -> None:
        """Consecutive type events on same selector should be collapsed to final value."""
        events = [
            make_event("type", [css_selector("#email")], value="t"),
            make_event("type", [css_selector("#email")], value="te"),
            make_event("type", [css_selector("#email")], value="tes"),
            make_event("type", [css_selector("#email")], value="test"),
        ]

        result = preprocess_events(events)

        assert len(result) == 1
        assert result[0]["event_type"] == "type"
        assert result[0]["selector"] == "#email"
        assert result[0]["value"] == "test"

    def test_preserves_type_events_on_different_selectors(self) -> None:
        """Type events on different selectors should not be collapsed together."""
        events = [
            make_event("type", [css_selector("#email")], value="user"),
            make_event("type", [css_selector("#password")], value="pass"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert result[0]["value"] == "user"
        assert result[1]["value"] == "pass"

    def test_removes_scroll_events(self) -> None:
        """Scroll events should be filtered out."""
        events = [
            make_event("click", [css_selector("#btn")]),
            make_event("scroll"),
            make_event("scroll"),
            make_event("click", [css_selector("#other")]),
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
            make_event("click", [css_selector("#start")]),
            make_event("type", [css_selector("#input")], value="final"),
        ]

        result = preprocess_events(events)

        assert len(result) == 2
        assert result[1]["value"] == "final"

    def test_includes_element_context(self) -> None:
        """Element context should be included when available."""
        events = [
            make_event(
                "click",
                [role_selector("button", "Submit")],
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

    def test_uses_best_selector(self) -> None:
        """Should use the best selector from the list."""
        events = [
            make_event(
                "click",
                [
                    css_selector("#btn"),
                    role_selector("button", "Login"),
                ],
            ),
        ]

        result = preprocess_events(events)

        assert result[0]["selector"] == 'role=button[name="Login"]'

    def test_fallback_to_coordinates_without_selector(self) -> None:
        """Should include coordinates when no selector is available."""
        events = [
            make_event("click", [], x=100, y=200),
        ]

        result = preprocess_events(events)

        assert result[0]["x"] == 100
        assert result[0]["y"] == 200

    def test_iframe_context_included(self) -> None:
        """Iframe events should include frame context."""
        events = [
            make_event(
                "click",
                [css_selector("#btn")],
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

        events = [make_event(t, [css_selector("#el")]) for t in event_types]
        result = preprocess_events(events)

        # Scroll is filtered out
        assert len(result) == 10
        result_types = [e["event_type"] for e in result]
        assert "scroll" not in result_types
