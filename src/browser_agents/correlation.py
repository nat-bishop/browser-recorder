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


def filter_network_requests(requests: list[NetworkRequest]) -> list[NetworkRequest]:
    """Filter out static assets and analytics requests.

    Keeps only meaningful requests: API calls, page loads, form submissions.

    Args:
        requests: Raw list of network requests

    Returns:
        Filtered list with static assets and analytics removed
    """
    filtered = []
    for req in requests:
        # Skip static assets by MIME type
        if req.mime_type:
            mime_lower = req.mime_type.lower()
            if any(mime in mime_lower for mime in STATIC_ASSET_MIMES):
                continue

        # Skip analytics/tracking domains
        try:
            parsed = urlparse(req.url)
            domain = parsed.netloc.lower()
            if any(analytics in domain for analytics in ANALYTICS_DOMAINS):
                continue
        except Exception:
            pass  # Keep request if URL parsing fails

        filtered.append(req)

    return filtered


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


# Risk level ordering for comparison
_RISK_ORDER = {
    RiskLevel.NONE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
}


def _risk_level_greater(a: RiskLevel, b: RiskLevel) -> bool:
    """Check if risk level a is greater than risk level b."""
    return _RISK_ORDER[a] > _RISK_ORDER[b]


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
            if _risk_level_greater(RiskLevel.HIGH, max_risk):
                max_risk = RiskLevel.HIGH
            reasons.append(f"DELETE request to {req.url[:50]}")
        elif req.method in ("POST", "PUT", "PATCH"):
            if _risk_level_greater(RiskLevel.LOW, max_risk):
                max_risk = RiskLevel.LOW

        # Check URL patterns for high risk
        for pattern in HIGH_RISK_PATTERNS:
            if re.search(pattern, url_lower):
                max_risk = RiskLevel.HIGH
                reasons.append(f"High-risk endpoint: {pattern}")
                break

        # Check URL patterns for medium risk
        if max_risk != RiskLevel.HIGH:
            for pattern in MEDIUM_RISK_PATTERNS:
                if re.search(pattern, url_lower):
                    if _risk_level_greater(RiskLevel.MEDIUM, max_risk):
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
                    is_state_changing=any(
                        r.method in ("POST", "PUT", "PATCH", "DELETE") for r in requests
                    ),
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
                is_state_changing=any(
                    r.method in ("POST", "PUT", "PATCH", "DELETE")
                    for r in initial_requests
                ),
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
                is_state_changing=any(
                    r.method in ("POST", "PUT", "PATCH", "DELETE") for r in triggered
                ),
                risk_level=risk_level,
                risk_reason=risk_reason,
            )
        )

    return correlated
