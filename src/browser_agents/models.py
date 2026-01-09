"""Pydantic models for recorded browser events, actions, and workflows."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class StepAction(str, Enum):
    """Typed action types for workflow steps."""

    navigate = "navigate"
    click = "click"
    type = "type"
    select = "select"  # For <select> dropdown elements
    scroll = "scroll"
    wait = "wait"


# Legacy type alias for backward compatibility during transition
EventType = Literal["click", "type", "navigate", "scroll", "wait"]


class RecordedEvent(BaseModel):
    """A single recorded browser event."""

    timestamp: float = Field(description="Unix timestamp when event occurred")
    event_type: EventType = Field(description="Type of browser event")
    # For click/type events
    selector: str | None = Field(
        default=None, description="CSS selector for target element"
    )
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
    # Screenshot taken after this event (path relative to workflow dir)
    screenshot_path: str | None = Field(
        default=None, description="Screenshot after this event"
    )


class Recording(BaseModel):
    """A complete recording session."""

    session_id: str = Field(description="Unique identifier for this recording session")
    start_url: str = Field(description="Initial URL where recording started")
    started_at: datetime = Field(description="When recording started")
    events: list[RecordedEvent] = Field(
        default_factory=list, description="Recorded events"
    )


# =============================================================================
# Action Definitions (Phase 3: LLM-generated from recordings)
# =============================================================================


class ActionParameter(BaseModel):
    """A parameter extracted from a recording for action substitution."""

    name: str = Field(
        description="Parameter name in snake_case (e.g., 'username', 'email')"
    )
    description: str = Field(description="What this parameter represents")
    example: str = Field(description="Example value extracted from the recording")


class ActionStep(BaseModel):
    """A single step in an action workflow."""

    action: StepAction = Field(
        description="Action type: navigate, click, type, select, scroll, wait"
    )
    target: str | None = Field(
        default=None, description="CSS selector or URL for the action"
    )
    value: str | None = Field(
        default=None,
        description="Value with {param_name} placeholders for substitution",
    )
    description: str = Field(description="Human-readable description of this step")
    # Fallback data for selector resilience (Phase 6: Vision LLM)
    fallback_coords: list[int] | None = Field(
        default=None, description="Backup click coordinates [x, y] if selector fails"
    )
    fallback_text: str | None = Field(
        default=None, description="Visible text of button/link for visual matching"
    )
    # Expected page state after this step (from recording screenshots)
    expected_screenshot: str | None = Field(
        default=None, description="Screenshot showing expected state after this step"
    )


class ActionDefinition(BaseModel):
    """A reusable browser action definition converted from a recording.

    This is the output of LLM-based recording analysis. It contains:
    - A descriptive name and purpose
    - Extracted parameters that can be substituted
    - Simplified steps (3-10) instead of raw events
    - Domain restrictions for safety
    """

    name: str = Field(
        description="Action name in snake_case (e.g., 'checkout_flow', 'login_user')"
    )
    description: str = Field(description="What this action accomplishes")
    parameters: list[ActionParameter] = Field(
        default_factory=list,
        description="Extracted variable parameters for substitution",
    )
    steps: list[ActionStep] = Field(
        description="Ordered steps to execute (typically 3-10)"
    )
    domains: list[str] = Field(description="Allowed domains for safety validation")


# =============================================================================
# Error Diagnosis (LLM-generated from failed step)
# =============================================================================


class ProposedFix(BaseModel):
    """A concrete fix the LLM proposes based on page HTML analysis.

    Used when the LLM can identify the correct selector or action
    from the current page state.
    """

    fix_type: Literal["modify_selector", "change_action", "delete_step"] = Field(
        description="Type of fix: modify_selector (use different selector), "
        "change_action (e.g., select instead of type), delete_step (remove this step)"
    )
    new_target: str | None = Field(
        default=None, description="New CSS selector to use (must exist in page HTML)"
    )
    new_action: str | None = Field(
        default=None,
        description="New action type if changing (e.g., 'select' instead of 'type')",
    )
    new_value: str | None = Field(default=None, description="New value if changing")
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence level: high (selector found in HTML), "
        "medium (inferred from context), low (best guess)"
    )
    reasoning: str = Field(description="Why this fix should work")


class ErrorDiagnosis(BaseModel):
    """LLM-generated diagnosis of why a step failed.

    Used during guided replay to classify errors and provide
    actionable suggestions to the user.
    """

    error_type: Literal["conversion", "execution", "verification"] = Field(
        description="Error category: conversion (LLM generated wrong step), "
        "execution (step correct but failed), verification (step ran, wrong result)"
    )
    explanation: str = Field(
        description="Plain-language explanation of what went wrong"
    )
    suggestion: str = Field(description="What the user should do to fix it")
    likely_cause: str = Field(description="Assessment of the root cause")
    proposed_fix: ProposedFix | None = Field(
        default=None,
        description="Concrete fix based on page HTML analysis. "
        "Only present when LLM has confidence in a fix.",
    )


class StepFixSuggestion(BaseModel):
    """LLM-generated suggestion for fixing a step based on user feedback.

    Used during guided replay when user describes the problem in natural language.
    """

    fix_type: Literal["delete", "modify", "keep"] = Field(
        description="What to do: delete (remove step), modify (change it), keep (retry as-is)"
    )
    explanation: str = Field(description="Why this fix was suggested")
    # For modify: the corrected step details
    new_action: str | None = Field(
        default=None, description="New action type (if modifying)"
    )
    new_target: str | None = Field(
        default=None, description="New target selector (if modifying)"
    )
    new_value: str | None = Field(default=None, description="New value (if modifying)")
    new_description: str | None = Field(
        default=None, description="New description (if modifying)"
    )


# =============================================================================
# Workflow: Unified format combining recording + action + media
# =============================================================================


class MediaRefs(BaseModel):
    """References to media files associated with a workflow."""

    video: str | None = Field(default=None, description="Path to screen recording file")
    audio: str | None = Field(default=None, description="Path to audio recording file")
    transcript: list[dict] | None = Field(
        default=None, description="Timestamped transcript from audio"
    )


class SuccessCondition(BaseModel):
    """Defines what success looks like for a workflow replay."""

    description: str = Field(
        description="Human-readable description of success (e.g., 'Order confirmation page')"
    )
    url_pattern: str | None = Field(
        default=None, description="Optional regex pattern for expected final URL"
    )
    screenshot_path: str | None = Field(
        default=None, description="Optional screenshot of expected final state"
    )


class Workflow(BaseModel):
    """Unified workflow combining raw recording, derived actions, and media.

    This is the single source of truth for a browser automation workflow:
    - Human-readable name and description
    - Raw events from recording (always present)
    - LLM-derived actions (multiple allowed, added by convert command)
    - Media references (optional, for video/audio capture)
    """

    id: str = Field(description="Unique session identifier")
    version: int = Field(default=2, description="Schema version for migrations")
    name: str | None = Field(default=None, description="Human-readable workflow name")
    description: str | None = Field(default=None, description="What this workflow does")
    source_url: str = Field(description="Initial URL where recording started")
    created_at: datetime = Field(description="When workflow was created")

    # Raw browser events (always present after recording)
    events: list[RecordedEvent] = Field(
        default_factory=list, description="Raw recorded browser events"
    )

    # LLM-derived actions (added by convert command, multiple allowed)
    actions: list[ActionDefinition] = Field(
        default_factory=list, description="Parameterized actions derived from events"
    )

    # Media references (optional, for future video/audio capture)
    media: MediaRefs | None = Field(
        default=None, description="References to associated media files"
    )

    # Success condition (optional, defines what success looks like)
    success_condition: SuccessCondition | None = Field(
        default=None, description="What success looks like for replay verification"
    )

    # Legacy support: accept 'action' field and convert to 'actions'
    def __init__(self, **data):
        # Handle legacy 'action' field (singular)
        if "action" in data and data["action"] is not None:
            if "actions" not in data or not data["actions"]:
                data["actions"] = [data["action"]]
            del data["action"]
        super().__init__(**data)
