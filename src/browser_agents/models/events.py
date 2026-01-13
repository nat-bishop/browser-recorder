"""UI event models for recording browser interactions."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class UIEventType(str, Enum):
    """All supported UI event types."""

    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    CLEAR = "clear"
    SELECT_OPTION = "select_option"
    CHECK = "check"
    UNCHECK = "uncheck"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    KEY_PRESS = "key_press"


class UIEvent(BaseModel):
    """A user interaction event - clean, focused schema.

    Each event captures:
    - What happened (event_type)
    - Where it happened (url, selector)
    - When it happened (timestamp, relative_time_ms)
    - Context for LLM understanding (element_type, label, etc.)
    """

    id: str = Field(description="Unique event ID (UUID)")
    timestamp: datetime = Field(description="When event occurred (UTC)")
    relative_time_ms: int = Field(description="Milliseconds since session start")

    event_type: UIEventType = Field(description="Type of UI interaction")
    url: str = Field(description="Page URL when event occurred")

    # Playwright selector string
    selector: str | None = Field(
        default=None, description="Playwright selector for the target element"
    )

    # Element context for LLM understanding
    element_type: (
        Literal[
            "button",
            "link",
            "input",
            "checkbox",
            "radio",
            "select",
            "textarea",
            "generic",
        ]
        | None
    ) = Field(default=None, description="Type of HTML element interacted with")
    element_label: str | None = Field(
        default=None, max_length=200, description="Associated label text"
    )
    element_text: str | None = Field(
        default=None, max_length=200, description="Inner text for buttons/links"
    )
    input_type: str | None = Field(
        default=None, description="Input type attribute (password, email, text, etc.)"
    )
    placeholder: str | None = Field(
        default=None, description="Placeholder text for inputs"
    )

    # Event-specific data
    value: str | None = Field(
        default=None, description="Value for type/select_option events"
    )
    key: str | None = Field(
        default=None, description="Key for key_press events (Enter, Tab, etc.)"
    )
    scroll_x: int | None = Field(default=None, description="Horizontal scroll position")
    scroll_y: int | None = Field(default=None, description="Vertical scroll position")

    # Iframe context
    frame_type: Literal["main", "iframe"] = Field(
        default="main", description="Whether event occurred in main frame or iframe"
    )
    frame_src: str | None = Field(
        default=None, description="Iframe src URL if in iframe"
    )
