"""Pydantic models for recorded browser events and action definitions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Event type used in both RecordedEvent and ActionStep
EventType = Literal["click", "type", "navigate", "scroll", "wait"]


class RecordedEvent(BaseModel):
    """A single recorded browser event."""

    timestamp: float = Field(description="Unix timestamp when event occurred")
    event_type: EventType = Field(description="Type of browser event")
    # For click/type events
    selector: str | None = Field(default=None, description="CSS selector for target element")
    # For type events
    value: str | None = Field(default=None, description="Text that was typed")
    # For navigate events
    url: str | None = Field(default=None, description="URL navigated to")
    # For scroll events
    scroll_x: int | None = Field(default=None, description="Horizontal scroll position")
    scroll_y: int | None = Field(default=None, description="Vertical scroll position")
    # For click events - backup if selector fails
    x: int | None = Field(default=None, description="Click X coordinate")
    y: int | None = Field(default=None, description="Click Y coordinate")


class Recording(BaseModel):
    """A complete recording session."""

    session_id: str = Field(description="Unique identifier for this recording session")
    start_url: str = Field(description="Initial URL where recording started")
    started_at: datetime = Field(description="When recording started")
    events: list[RecordedEvent] = Field(default_factory=list, description="Recorded events")


# =============================================================================
# Action Definitions (Phase 3: LLM-generated from recordings)
# =============================================================================


class ActionParameter(BaseModel):
    """A parameter extracted from a recording for action substitution."""

    name: str = Field(description="Parameter name in snake_case (e.g., 'username', 'email')")
    description: str = Field(description="What this parameter represents")
    example: str = Field(description="Example value extracted from the recording")


class ActionStep(BaseModel):
    """A single step in an action workflow."""

    action: EventType = Field(description="Action type: navigate, click, type, scroll, wait")
    target: str | None = Field(default=None, description="CSS selector or URL for the action")
    value: str | None = Field(
        default=None, description="Value with {param_name} placeholders for substitution"
    )
    description: str = Field(description="Human-readable description of this step")


class ActionDefinition(BaseModel):
    """A reusable browser action definition converted from a recording.

    This is the output of LLM-based recording analysis. It contains:
    - A descriptive name and purpose
    - Extracted parameters that can be substituted
    - Simplified steps (3-10) instead of raw events
    - Domain restrictions for safety
    """

    name: str = Field(description="Action name in snake_case (e.g., 'checkout_flow', 'login_user')")
    description: str = Field(description="What this action accomplishes")
    parameters: list[ActionParameter] = Field(
        default_factory=list, description="Extracted variable parameters for substitution"
    )
    steps: list[ActionStep] = Field(description="Ordered steps to execute (typically 3-10)")
    domains: list[str] = Field(description="Allowed domains for safety validation")
