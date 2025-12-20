"""Pydantic models for recorded browser events."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RecordedEvent(BaseModel):
    """A single recorded browser event."""

    timestamp: float = Field(description="Unix timestamp when event occurred")
    event_type: Literal["click", "type", "navigate", "scroll", "wait"] = Field(
        description="Type of browser event"
    )
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
