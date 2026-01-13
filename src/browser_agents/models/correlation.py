"""Correlation models for linking UI events with network requests."""

from enum import Enum

from pydantic import BaseModel, Field

from browser_agents.models.events import UIEvent
from browser_agents.models.network import NetworkRequest


class RiskLevel(str, Enum):
    """Risk level for network-based danger detection."""

    NONE = "none"  # GET requests, static pages
    LOW = "low"  # Non-destructive POSTs
    MEDIUM = "medium"  # Auth, profile changes
    HIGH = "high"  # Financial, deletion, admin


class CorrelatedAction(BaseModel):
    """A UI event paired with its network effects.

    This unified model links what the user did (UI event) with what the browser
    sent (network requests). This enables:
    - Richer LLM context (understand both UI and API)
    - Validation (compare recorded vs replayed network)
    - Danger detection (flag risky operations)
    """

    event: UIEvent | None = Field(
        default=None,
        description="The UI event that triggered network activity (None for initial page load)",
    )
    network_requests: list[NetworkRequest] = Field(
        default_factory=list,
        description="Network requests triggered by this event",
    )
    api_endpoints: list[str] = Field(
        default_factory=list,
        description="Unique API paths extracted from requests (e.g., '/api/auth')",
    )
    is_state_changing: bool = Field(
        default=False,
        description="True if any POST/PUT/PATCH/DELETE requests were made",
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.NONE,
        description="Computed risk level based on network analysis",
    )
    risk_reason: str | None = Field(
        default=None,
        description="Explanation of why this action is risky",
    )
