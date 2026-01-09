"""Action and workflow models for LLM-derived browser automations.

These models represent the processed output from LLM conversion:
- ActionDefinition: Parameterized, reusable workflow
- ActionStep: Individual step in a workflow
- ActionParameter: Extracted parameter for substitution

Note: Raw recording events use UIEvent from events.py.
These models are for the LLM-processed output.
"""

from enum import Enum

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
