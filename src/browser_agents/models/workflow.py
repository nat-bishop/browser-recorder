"""Action and workflow models for LLM-derived browser automations.

These models represent the processed output from LLM conversion:
- ActionDefinition: Parameterized, reusable workflow
- ActionStep: Individual step in a workflow
- ActionParameter: Extracted parameter for substitution

Note: Raw recording events use UIEvent from events.py.
These models are for the LLM-processed output.
"""

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


class ActionParameter(BaseModel):
    """A parameter extracted from a recording for action substitution."""

    name: str = Field(
        description="Parameter name in snake_case (e.g., 'username', 'email')"
    )
    description: str = Field(description="What this parameter represents")
    example: str = Field(description="Example value extracted from the recording")
    is_sensitive: bool = Field(
        default=False, description="Whether this is sensitive data (password, etc.)"
    )


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
    # Fallback data for selector resilience
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
    """A concrete fix the LLM proposes based on page HTML analysis."""

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
    """LLM-generated diagnosis of why a step failed."""

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
        description="Concrete fix based on page HTML analysis.",
    )


class StepFixSuggestion(BaseModel):
    """LLM-generated suggestion for fixing a step based on user feedback."""

    fix_type: Literal["delete", "modify", "keep"] = Field(
        description="What to do: delete (remove step), modify (change it), keep (retry as-is)"
    )
    explanation: str = Field(description="Why this fix was suggested")
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
# Supporting types
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
