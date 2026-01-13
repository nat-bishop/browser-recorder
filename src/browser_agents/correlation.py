"""Correlation logic for linking UI events with network requests.

This module provides:
- Network request filtering (remove static assets, analytics)
- Event-network correlation (match requests to triggering events)
- Risk level computation (detect dangerous operations)
"""

import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from browser_agents.models import (
    CorrelatedAction,
    NetworkRequest,
    RiskLevel,
    UIEvent,
)

# MIME types for static assets to filter out
STATIC_ASSET_MIMES = {
    "application/javascript",
    "text/javascript",
    "text/css",
    "image/",
    "font/",
    "video/",
    "audio/",
}

# Analytics/tracking domains to filter out
ANALYTICS_DOMAINS = {
    "google-analytics.com",
    "googletagmanager.com",
    "segment.io",
    "segment.com",
    "mixpanel.com",
    "hotjar.com",
    "optimizely.com",
    "facebook.net",
    "doubleclick.net",
    "clarity.ms",
    "newrelic.com",
    "sentry.io",
}

# URL patterns indicating high-risk operations
HIGH_RISK_PATTERNS = [
    r"/delete",
    r"/remove",
    r"/cancel",
    r"/terminate",
    r"/payment",
    r"/checkout",
    r"/order",
    r"/purchase",
    r"/transfer",
    r"/withdraw",
    r"/admin",
    r"/sudo",
]

# URL patterns indicating medium-risk operations
MEDIUM_RISK_PATTERNS = [
    r"/auth",
    r"/login",
    r"/logout",
    r"/password",
    r"/reset",
    r"/profile",
    r"/settings",
    r"/account",
    r"/subscribe",
    r"/unsubscribe",
]

# Patterns in request/response body indicating sensitive data
SENSITIVE_BODY_PATTERNS = [
    r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",  # Credit card numbers
    r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
    r"(api[_-]?key|secret|token|password)[\"']?\s*[:=]",  # API keys/secrets
]

# HTTP methods that modify server state
STATE_CHANGING_METHODS = frozenset(("POST", "PUT", "PATCH", "DELETE"))


def _has_state_changing_request(requests: list[NetworkRequest]) -> bool:
    """Check if any request uses a state-changing HTTP method."""
    return any(r.method in STATE_CHANGING_METHODS for r in requests)


def _is_static_asset(req: NetworkRequest) -> bool:
    """Check if request is for a static asset based on MIME type."""
    if not req.mime_type:
        return False
    mime_lower = req.mime_type.lower()
    return any(mime in mime_lower for mime in STATIC_ASSET_MIMES)


def _is_analytics_request(req: NetworkRequest) -> bool:
    """Check if request is to an analytics/tracking domain."""
    try:
        domain = urlparse(req.url).netloc.lower()
        return any(analytics in domain for analytics in ANALYTICS_DOMAINS)
    except Exception:
        return False


def filter_network_requests(requests: list[NetworkRequest]) -> list[NetworkRequest]:
    """Filter out static assets and analytics requests.

    Keeps only meaningful requests: API calls, page loads, form submissions.
    """
    return [
        req
        for req in requests
        if not _is_static_asset(req) and not _is_analytics_request(req)
    ]


def extract_api_endpoints(requests: list[NetworkRequest]) -> list[str]:
    """Extract unique API paths from network requests.

    Args:
        requests: List of network requests

    Returns:
        List of unique API paths (e.g., ['/api/auth', '/api/users'])
    """
    endpoints = set()
    for req in requests:
        try:
            parsed = urlparse(req.url)
            # Only include paths that look like API endpoints
            path = parsed.path
            if path and not path.endswith(
                (".js", ".css", ".png", ".jpg", ".gif", ".ico")
            ):
                endpoints.add(path)
        except Exception:
            pass
    return sorted(endpoints)


def compute_risk(requests: list[NetworkRequest]) -> tuple[RiskLevel, str | None]:
    """Compute risk level from network requests.

    Analyzes HTTP methods, URL patterns, and body content to detect
    potentially dangerous operations.

    Args:
        requests: List of network requests to analyze

    Returns:
        Tuple of (RiskLevel, reason string or None)
    """
    reasons: list[str] = []
    max_risk = RiskLevel.NONE

    for req in requests:
        url_lower = req.url.lower()

        # Check HTTP method
        if req.method == "DELETE":
            if max_risk < RiskLevel.HIGH:
                max_risk = RiskLevel.HIGH
            reasons.append(f"DELETE request to {req.url[:50]}")
        elif req.method in ("POST", "PUT", "PATCH"):
            if max_risk < RiskLevel.LOW:
                max_risk = RiskLevel.LOW

        # Check URL patterns for high risk
        for pattern in HIGH_RISK_PATTERNS:
            if re.search(pattern, url_lower):
                max_risk = RiskLevel.HIGH
                reasons.append(f"High-risk endpoint: {pattern}")
                break

        # Check URL patterns for medium risk
        if max_risk < RiskLevel.HIGH:
            for pattern in MEDIUM_RISK_PATTERNS:
                if re.search(pattern, url_lower):
                    if max_risk < RiskLevel.MEDIUM:
                        max_risk = RiskLevel.MEDIUM
                    reasons.append(f"Sensitive endpoint: {pattern}")
                    break

        # Check response body for sensitive data patterns
        if req.response_body:
            try:
                body_str = req.response_body.decode("utf-8", errors="ignore")
                for pattern in SENSITIVE_BODY_PATTERNS:
                    if re.search(pattern, body_str, re.IGNORECASE):
                        max_risk = RiskLevel.HIGH
                        reasons.append("Contains sensitive data pattern")
                        break
            except Exception:
                pass

    return max_risk, "; ".join(reasons) if reasons else None


def correlate_events_with_network(
    events: list[UIEvent],
    requests: list[NetworkRequest],
    session_start: datetime,
    max_window_seconds: float = 2.0,
) -> list[CorrelatedAction]:
    """Match network requests to the UI events that triggered them.

    Uses timestamp-based correlation: requests that started within a time window
    after an event are attributed to that event. The window extends until the
    next event or max_window_seconds, whichever is smaller.

    Args:
        events: List of UI events (sorted by relative_time_ms)
        requests: List of network requests (will be sorted by timestamp)
        session_start: Session start time for calculating absolute event times
        max_window_seconds: Maximum time window for correlation (default 2s)

    Returns:
        List of CorrelatedAction objects, one per event plus initial load
    """
    if not events:
        # No events - return single action with all requests as initial load
        if requests:
            risk_level, risk_reason = compute_risk(requests)
            return [
                CorrelatedAction(
                    event=None,
                    network_requests=requests,
                    api_endpoints=extract_api_endpoints(requests),
                    is_state_changing=_has_state_changing_request(requests),
                    risk_level=risk_level,
                    risk_reason=risk_reason,
                )
            ]
        return []

    # Sort events by relative time and requests by timestamp
    sorted_events = sorted(events, key=lambda e: e.relative_time_ms)
    sorted_requests = sorted(requests, key=lambda r: r.timestamp)

    correlated: list[CorrelatedAction] = []
    max_window = timedelta(seconds=max_window_seconds)

    # Handle requests before first event (initial page load)
    first_event_time = session_start + timedelta(
        milliseconds=sorted_events[0].relative_time_ms
    )
    initial_requests = [r for r in sorted_requests if r.timestamp < first_event_time]
    if initial_requests:
        risk_level, risk_reason = compute_risk(initial_requests)
        correlated.append(
            CorrelatedAction(
                event=None,  # No UI event - initial load
                network_requests=initial_requests,
                api_endpoints=extract_api_endpoints(initial_requests),
                is_state_changing=_has_state_changing_request(initial_requests),
                risk_level=risk_level,
                risk_reason=risk_reason,
            )
        )

    # Correlate each event with its triggered requests
    for i, event in enumerate(sorted_events):
        # Calculate absolute event time
        event_time = session_start + timedelta(milliseconds=event.relative_time_ms)

        # Window ends at next event time or max_window, whichever is smaller
        if i + 1 < len(sorted_events):
            next_event_time = session_start + timedelta(
                milliseconds=sorted_events[i + 1].relative_time_ms
            )
            window_end = min(next_event_time, event_time + max_window)
        else:
            window_end = event_time + max_window

        # Find requests in window (use START time for correlation)
        triggered = [
            r for r in sorted_requests if event_time <= r.timestamp < window_end
        ]

        # Compute risk level for this action
        risk_level, risk_reason = compute_risk(triggered)

        correlated.append(
            CorrelatedAction(
                event=event,
                network_requests=triggered,
                api_endpoints=extract_api_endpoints(triggered),
                is_state_changing=_has_state_changing_request(triggered),
                risk_level=risk_level,
                risk_reason=risk_reason,
            )
        )

    return correlated
