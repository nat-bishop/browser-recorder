"""Tests for the correlation module.

Tests cover:
- Network request filtering (static assets, analytics)
- Event-network correlation (timestamp-based)
- Risk level computation (URL patterns, methods, body content)
- Edge cases (empty inputs, long-running requests, rapid events)
"""

from datetime import UTC, datetime, timedelta

import pytest

from browser_agents.correlation import (
    ANALYTICS_DOMAINS,
    compute_risk,
    correlate_events_with_network,
    extract_api_endpoints,
    filter_network_requests,
)
from browser_agents.models import (
    CorrelatedAction,
    NetworkRequest,
    RiskLevel,
    UIEvent,
    UIEventType,
)


# Helper to create test events
def make_event(
    event_type: UIEventType = UIEventType.CLICK,
    relative_time_ms: int = 0,
    selector: str | None = "#test",
) -> UIEvent:
    return UIEvent(
        id="test-id",
        timestamp=datetime.now(tz=UTC),  # Will be ignored - relative_time_ms used
        relative_time_ms=relative_time_ms,
        event_type=event_type,
        url="https://example.com",
        selector=selector,
    )


# Helper to create test network requests
def make_request(
    url: str = "https://example.com/api/test",
    method: str = "GET",
    status: int = 200,
    mime_type: str | None = "application/json",
    timestamp: datetime | None = None,
    response_body: bytes | None = None,
) -> NetworkRequest:
    return NetworkRequest(
        timestamp=timestamp or datetime.now(tz=UTC),
        method=method,
        url=url,
        status=status,
        mime_type=mime_type,
        response_body=response_body,
    )


class TestFilterNetworkRequests:
    """Tests for filter_network_requests()."""

    def test_keeps_api_requests(self):
        """API requests with JSON mime type should be kept."""
        requests = [
            make_request(
                url="https://api.example.com/users",
                mime_type="application/json",
            )
        ]
        filtered = filter_network_requests(requests)
        assert len(filtered) == 1
        assert filtered[0].url == "https://api.example.com/users"

    def test_removes_javascript(self):
        """JavaScript files should be filtered out."""
        requests = [
            make_request(
                url="https://example.com/app.js",
                mime_type="application/javascript",
            ),
            make_request(
                url="https://example.com/bundle.js",
                mime_type="text/javascript",
            ),
        ]
        filtered = filter_network_requests(requests)
        assert len(filtered) == 0

    def test_removes_css(self):
        """CSS files should be filtered out."""
        requests = [
            make_request(
                url="https://example.com/styles.css",
                mime_type="text/css",
            )
        ]
        filtered = filter_network_requests(requests)
        assert len(filtered) == 0

    def test_removes_images(self):
        """Image files should be filtered out."""
        requests = [
            make_request(url="https://example.com/logo.png", mime_type="image/png"),
            make_request(url="https://example.com/photo.jpg", mime_type="image/jpeg"),
        ]
        filtered = filter_network_requests(requests)
        assert len(filtered) == 0

    def test_removes_fonts(self):
        """Font files should be filtered out."""
        requests = [
            make_request(
                url="https://example.com/font.woff2",
                mime_type="font/woff2",
            )
        ]
        filtered = filter_network_requests(requests)
        assert len(filtered) == 0

    @pytest.mark.parametrize("domain", list(ANALYTICS_DOMAINS)[:5])
    def test_removes_analytics_domains(self, domain: str):
        """Analytics and tracking domains should be filtered out."""
        requests = [
            make_request(
                url=f"https://{domain}/track",
                mime_type="application/json",
            )
        ]
        filtered = filter_network_requests(requests)
        assert len(filtered) == 0

    def test_keeps_html_page_loads(self):
        """HTML page loads should be kept."""
        requests = [
            make_request(
                url="https://example.com/dashboard",
                mime_type="text/html",
            )
        ]
        filtered = filter_network_requests(requests)
        assert len(filtered) == 1

    def test_keeps_requests_with_no_mime_type(self):
        """Requests without mime type should be kept (might be API calls)."""
        requests = [
            make_request(
                url="https://api.example.com/data",
                mime_type=None,
            )
        ]
        filtered = filter_network_requests(requests)
        assert len(filtered) == 1

    def test_empty_input_returns_empty(self):
        """Empty input should return empty list."""
        filtered = filter_network_requests([])
        assert filtered == []

    def test_mixed_requests(self):
        """Mixed requests should filter correctly."""
        requests = [
            make_request(
                url="https://example.com/api/users", mime_type="application/json"
            ),
            make_request(
                url="https://example.com/app.js", mime_type="application/javascript"
            ),
            make_request(
                url="https://google-analytics.com/collect", mime_type="text/plain"
            ),
            make_request(url="https://example.com/page", mime_type="text/html"),
        ]
        filtered = filter_network_requests(requests)
        assert len(filtered) == 2
        urls = [r.url for r in filtered]
        assert "https://example.com/api/users" in urls
        assert "https://example.com/page" in urls


class TestExtractApiEndpoints:
    """Tests for extract_api_endpoints()."""

    def test_extracts_paths(self):
        """Should extract paths from URLs."""
        requests = [
            make_request(url="https://api.example.com/users"),
            make_request(url="https://api.example.com/posts"),
        ]
        endpoints = extract_api_endpoints(requests)
        assert "/users" in endpoints
        assert "/posts" in endpoints

    def test_deduplicates_paths(self):
        """Should deduplicate identical paths."""
        requests = [
            make_request(url="https://api.example.com/users"),
            make_request(url="https://api.example.com/users"),
        ]
        endpoints = extract_api_endpoints(requests)
        assert endpoints.count("/users") == 1

    def test_excludes_static_extensions(self):
        """Should exclude paths with static file extensions."""
        requests = [
            make_request(url="https://example.com/bundle.js"),
            make_request(url="https://example.com/styles.css"),
            make_request(url="https://example.com/logo.png"),
        ]
        endpoints = extract_api_endpoints(requests)
        # All should be excluded
        assert len(endpoints) == 0

    def test_returns_sorted(self):
        """Should return sorted list."""
        requests = [
            make_request(url="https://api.example.com/zebra"),
            make_request(url="https://api.example.com/alpha"),
        ]
        endpoints = extract_api_endpoints(requests)
        assert endpoints == ["/alpha", "/zebra"]


class TestComputeRisk:
    """Tests for compute_risk()."""

    def test_get_requests_are_none_risk(self):
        """GET requests should be NONE risk."""
        requests = [make_request(method="GET")]
        risk, _reason = compute_risk(requests)
        assert risk == RiskLevel.NONE

    def test_post_requests_are_low_risk(self):
        """POST requests without dangerous patterns are LOW risk."""
        requests = [make_request(method="POST", url="https://example.com/api/comments")]
        risk, _reason = compute_risk(requests)
        assert risk == RiskLevel.LOW

    def test_delete_requests_are_high_risk(self):
        """DELETE requests should be HIGH risk."""
        requests = [
            make_request(method="DELETE", url="https://example.com/api/user/123")
        ]
        risk, reason = compute_risk(requests)
        assert risk == RiskLevel.HIGH
        assert "DELETE" in reason

    def test_payment_endpoint_is_high_risk(self):
        """Payment endpoints should be HIGH risk."""
        requests = [
            make_request(method="POST", url="https://example.com/api/payment/process")
        ]
        risk, reason = compute_risk(requests)
        assert risk == RiskLevel.HIGH
        assert "payment" in reason.lower()

    def test_checkout_endpoint_is_high_risk(self):
        """Checkout endpoints should be HIGH risk."""
        requests = [make_request(method="POST", url="https://example.com/checkout")]
        risk, _reason = compute_risk(requests)
        assert risk == RiskLevel.HIGH

    def test_delete_endpoint_is_high_risk(self):
        """Delete endpoints (in URL) should be HIGH risk."""
        requests = [
            make_request(method="POST", url="https://example.com/api/delete-account")
        ]
        risk, _reason = compute_risk(requests)
        assert risk == RiskLevel.HIGH

    def test_login_endpoint_is_medium_risk(self):
        """Login endpoints should be MEDIUM risk."""
        requests = [make_request(method="POST", url="https://example.com/api/login")]
        risk, reason = compute_risk(requests)
        assert risk == RiskLevel.MEDIUM
        assert "login" in reason.lower()

    def test_auth_endpoint_is_medium_risk(self):
        """Auth endpoints should be MEDIUM risk."""
        requests = [make_request(method="POST", url="https://example.com/auth/token")]
        risk, _reason = compute_risk(requests)
        assert risk == RiskLevel.MEDIUM

    def test_settings_endpoint_is_medium_risk(self):
        """Settings endpoints should be MEDIUM risk."""
        requests = [
            make_request(method="POST", url="https://example.com/user/settings")
        ]
        risk, _reason = compute_risk(requests)
        assert risk == RiskLevel.MEDIUM

    def test_credit_card_in_body_is_high_risk(self):
        """Credit card patterns in body should be HIGH risk."""
        requests = [
            make_request(
                method="POST",
                url="https://example.com/api/data",
                response_body=b'{"card": "4111-1111-1111-1111"}',
            )
        ]
        risk, reason = compute_risk(requests)
        assert risk == RiskLevel.HIGH
        assert "sensitive" in reason.lower()

    def test_ssn_in_body_is_high_risk(self):
        """SSN patterns in body should be HIGH risk."""
        requests = [
            make_request(
                method="GET",
                url="https://example.com/api/profile",
                response_body=b'{"ssn": "123-45-6789"}',
            )
        ]
        risk, _reason = compute_risk(requests)
        assert risk == RiskLevel.HIGH

    def test_api_key_in_body_is_high_risk(self):
        """API key patterns in body should be HIGH risk."""
        requests = [
            make_request(
                method="GET",
                url="https://example.com/api/config",
                response_body=b'api_key: "sk_live_abc123"',
            )
        ]
        risk, _reason = compute_risk(requests)
        assert risk == RiskLevel.HIGH

    def test_empty_requests_is_none_risk(self):
        """Empty request list should be NONE risk."""
        risk, reason = compute_risk([])
        assert risk == RiskLevel.NONE
        assert reason is None

    def test_multiple_requests_takes_highest_risk(self):
        """Multiple requests should return the highest risk level."""
        requests = [
            make_request(method="GET", url="https://example.com/page"),  # NONE
            make_request(method="POST", url="https://example.com/login"),  # MEDIUM
            make_request(method="DELETE", url="https://example.com/user"),  # HIGH
        ]
        risk, _reason = compute_risk(requests)
        assert risk == RiskLevel.HIGH


class TestCorrelateEventsWithNetwork:
    """Tests for correlate_events_with_network()."""

    def test_empty_events_returns_empty_or_initial_load(self):
        """Empty events should return empty list or single initial load."""
        session_start = datetime.now(tz=UTC)
        result = correlate_events_with_network([], [], session_start)
        assert result == []

        # With requests but no events, should create initial load action
        requests = [make_request(timestamp=session_start + timedelta(seconds=1))]
        result = correlate_events_with_network([], requests, session_start)
        assert len(result) == 1
        assert result[0].event is None

    def test_assigns_requests_to_triggering_event(self):
        """Requests should be assigned to the event that triggered them."""
        session_start = datetime.now(tz=UTC)

        events = [
            make_event(event_type=UIEventType.CLICK, relative_time_ms=0),
            make_event(event_type=UIEventType.CLICK, relative_time_ms=1000),
        ]

        # Request at 500ms should go to first event
        requests = [
            make_request(timestamp=session_start + timedelta(milliseconds=500)),
        ]

        result = correlate_events_with_network(events, requests, session_start)

        # Should have 2 actions (one per event)
        assert len(result) == 2
        assert len(result[0].network_requests) == 1
        assert len(result[1].network_requests) == 0

    def test_multiple_requests_per_event(self):
        """Multiple requests can be assigned to single event."""
        session_start = datetime.now(tz=UTC)

        events = [make_event(event_type=UIEventType.CLICK, relative_time_ms=0)]

        requests = [
            make_request(timestamp=session_start + timedelta(milliseconds=100)),
            make_request(timestamp=session_start + timedelta(milliseconds=200)),
            make_request(timestamp=session_start + timedelta(milliseconds=300)),
        ]

        result = correlate_events_with_network(events, requests, session_start)

        assert len(result) == 1
        assert len(result[0].network_requests) == 3

    def test_requests_before_first_event_as_initial_load(self):
        """Requests before first event should be in initial load action."""
        session_start = datetime.now(tz=UTC)

        events = [
            make_event(event_type=UIEventType.NAVIGATE, relative_time_ms=1000),
        ]

        # Requests at 500ms (before first event at 1000ms)
        requests = [
            make_request(timestamp=session_start + timedelta(milliseconds=500)),
        ]

        result = correlate_events_with_network(events, requests, session_start)

        # Should have 2 actions: initial load + navigate event
        assert len(result) == 2
        assert result[0].event is None  # Initial load
        assert len(result[0].network_requests) == 1
        assert result[1].event is not None  # Navigate event
        assert len(result[1].network_requests) == 0

    def test_respects_max_window(self):
        """Requests after max window should not be assigned to event."""
        session_start = datetime.now(tz=UTC)

        events = [make_event(event_type=UIEventType.CLICK, relative_time_ms=0)]

        # Request at 5 seconds (beyond default 2s window)
        requests = [
            make_request(timestamp=session_start + timedelta(seconds=5)),
        ]

        result = correlate_events_with_network(events, requests, session_start)

        assert len(result) == 1
        assert len(result[0].network_requests) == 0

    def test_window_bounded_by_next_event(self):
        """Window should end at next event time if sooner than max."""
        session_start = datetime.now(tz=UTC)

        # Events 500ms apart
        events = [
            make_event(event_type=UIEventType.CLICK, relative_time_ms=0),
            make_event(event_type=UIEventType.CLICK, relative_time_ms=500),
        ]

        # Request at 300ms should go to first event
        # Request at 600ms should go to second event
        requests = [
            make_request(
                url="https://example.com/first",
                timestamp=session_start + timedelta(milliseconds=300),
            ),
            make_request(
                url="https://example.com/second",
                timestamp=session_start + timedelta(milliseconds=600),
            ),
        ]

        result = correlate_events_with_network(events, requests, session_start)

        assert len(result) == 2
        assert len(result[0].network_requests) == 1
        assert result[0].network_requests[0].url == "https://example.com/first"
        assert len(result[1].network_requests) == 1
        assert result[1].network_requests[0].url == "https://example.com/second"

    def test_long_running_request_uses_start_time(self):
        """Long-running requests should use start time for correlation."""
        session_start = datetime.now(tz=UTC)

        events = [
            make_event(event_type=UIEventType.CLICK, relative_time_ms=0),
            make_event(event_type=UIEventType.CLICK, relative_time_ms=5000),
        ]

        # Request starts at 100ms, takes 5000ms (duration not used for correlation)
        # Should be assigned to first event based on start time
        requests = [
            make_request(
                timestamp=session_start + timedelta(milliseconds=100),
            ),
        ]

        result = correlate_events_with_network(events, requests, session_start)

        assert len(result[0].network_requests) == 1
        assert len(result[1].network_requests) == 0

    def test_computes_risk_per_action(self):
        """Each action should have computed risk level."""
        session_start = datetime.now(tz=UTC)

        events = [
            make_event(event_type=UIEventType.CLICK, relative_time_ms=0),
            make_event(event_type=UIEventType.CLICK, relative_time_ms=1000),
        ]

        requests = [
            make_request(
                url="https://example.com/api/login",
                method="POST",
                timestamp=session_start + timedelta(milliseconds=100),
            ),
            make_request(
                url="https://example.com/page",
                method="GET",
                timestamp=session_start + timedelta(milliseconds=1100),
            ),
        ]

        result = correlate_events_with_network(events, requests, session_start)

        assert result[0].risk_level == RiskLevel.MEDIUM  # login is medium risk
        assert result[1].risk_level == RiskLevel.NONE  # GET is no risk

    def test_sets_is_state_changing(self):
        """is_state_changing should be True for POST/PUT/PATCH/DELETE."""
        session_start = datetime.now(tz=UTC)

        events = [
            make_event(event_type=UIEventType.CLICK, relative_time_ms=0),
            make_event(event_type=UIEventType.CLICK, relative_time_ms=1000),
        ]

        requests = [
            make_request(
                method="POST", timestamp=session_start + timedelta(milliseconds=100)
            ),
            make_request(
                method="GET", timestamp=session_start + timedelta(milliseconds=1100)
            ),
        ]

        result = correlate_events_with_network(events, requests, session_start)

        assert result[0].is_state_changing is True
        assert result[1].is_state_changing is False

    def test_extracts_api_endpoints(self):
        """API endpoints should be extracted from requests."""
        session_start = datetime.now(tz=UTC)

        events = [make_event(event_type=UIEventType.CLICK, relative_time_ms=0)]

        requests = [
            make_request(
                url="https://example.com/api/users",
                timestamp=session_start + timedelta(milliseconds=100),
            ),
            make_request(
                url="https://example.com/api/posts",
                timestamp=session_start + timedelta(milliseconds=200),
            ),
        ]

        result = correlate_events_with_network(events, requests, session_start)

        assert "/api/users" in result[0].api_endpoints
        assert "/api/posts" in result[0].api_endpoints


class TestEnrichEventsWithNetwork:
    """Tests for enrich_events_with_network in converter."""

    def test_matches_by_event_id_not_position(self):
        """Enrichment should match by event ID, handling preprocessing that removes events."""
        from browser_agents.converter import (
            enrich_events_with_network,
            preprocess_events,
        )

        session_start = datetime.now(tz=UTC)

        # Create events: navigate, scroll (will be removed), click
        events = [
            UIEvent(
                id="event-1",
                timestamp=session_start,
                relative_time_ms=0,
                event_type=UIEventType.NAVIGATE,
                url="https://example.com",
            ),
            UIEvent(
                id="event-2",
                timestamp=session_start + timedelta(milliseconds=500),
                relative_time_ms=500,
                event_type=UIEventType.SCROLL,  # Will be removed by preprocessing
                url="https://example.com",
                scroll_x=0,
                scroll_y=100,
            ),
            UIEvent(
                id="event-3",
                timestamp=session_start + timedelta(milliseconds=1000),
                relative_time_ms=1000,
                event_type=UIEventType.CLICK,
                url="https://example.com",
                selector="#button",
            ),
        ]

        # Create correlated actions for all 3 events
        correlated = [
            CorrelatedAction(
                event=events[0],
                network_requests=[
                    make_request(
                        url="https://example.com/api/init",
                        mime_type="application/json",
                        timestamp=session_start + timedelta(milliseconds=100),
                    )
                ],
            ),
            CorrelatedAction(
                event=events[1],  # scroll event
                network_requests=[
                    make_request(
                        url="https://example.com/api/scroll-data",
                        mime_type="application/json",
                        timestamp=session_start + timedelta(milliseconds=600),
                    )
                ],
            ),
            CorrelatedAction(
                event=events[2],  # click event
                network_requests=[
                    make_request(
                        url="https://example.com/api/click",
                        mime_type="application/json",
                        timestamp=session_start + timedelta(milliseconds=1100),
                    )
                ],
            ),
        ]

        # Preprocess events (removes scroll)
        preprocessed = preprocess_events(events)
        assert len(preprocessed) == 2  # navigate and click, no scroll

        # Enrich with network
        enriched = enrich_events_with_network(preprocessed, correlated)

        # Verify navigate event got its own API call (not scroll's)
        assert enriched[0]["event_type"] == "navigate"
        assert "triggered_api_calls" in enriched[0]
        assert (
            enriched[0]["triggered_api_calls"][0]["url"]
            == "https://example.com/api/init"
        )

        # Verify click event got its own API call (not scroll's)
        assert enriched[1]["event_type"] == "click"
        assert "triggered_api_calls" in enriched[1]
        assert (
            enriched[1]["triggered_api_calls"][0]["url"]
            == "https://example.com/api/click"
        )

    def test_removes_internal_event_id(self):
        """Internal _event_id should be removed from enriched events."""
        from browser_agents.converter import enrich_events_with_network

        preprocessed = [
            {"_event_id": "test-id", "event_type": "click", "selector": "#btn"}
        ]
        enriched = enrich_events_with_network(preprocessed, [])

        assert "_event_id" not in enriched[0]
        assert enriched[0]["event_type"] == "click"


class TestCorrelatedActionModel:
    """Tests for CorrelatedAction model."""

    def test_default_values(self):
        """Default values should be set correctly."""
        action = CorrelatedAction()
        assert action.event is None
        assert action.network_requests == []
        assert action.api_endpoints == []
        assert action.is_state_changing is False
        assert action.risk_level == RiskLevel.NONE
        assert action.risk_reason is None

    def test_serialization_roundtrip(self):
        """CorrelatedAction should serialize and deserialize correctly."""
        event = make_event()
        request = make_request()

        action = CorrelatedAction(
            event=event,
            network_requests=[request],
            api_endpoints=["/api/test"],
            is_state_changing=True,
            risk_level=RiskLevel.MEDIUM,
            risk_reason="Test reason",
        )

        # Serialize and deserialize
        json_str = action.model_dump_json()
        restored = CorrelatedAction.model_validate_json(json_str)

        assert restored.event.id == event.id
        assert len(restored.network_requests) == 1
        assert restored.api_endpoints == ["/api/test"]
        assert restored.is_state_changing is True
        assert restored.risk_level == RiskLevel.MEDIUM
        assert restored.risk_reason == "Test reason"
