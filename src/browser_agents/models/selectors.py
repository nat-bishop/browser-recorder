"""Selector models for Codegen-style element identification."""

from typing import Literal

from pydantic import BaseModel, Field


class SelectorCandidate(BaseModel):
    """A single selector strategy with confidence level.

    Selectors are ordered by priority during playback:
    1. role - ARIA role + accessible name (most resilient)
    2. label - Associated label text (great for forms)
    3. placeholder - Input placeholder text
    4. text - Visible text content (for buttons/links)
    5. testid - data-testid attribute (stable but requires app support)
    6. css - CSS selector (fallback, most brittle)
    """

    strategy: Literal["role", "label", "placeholder", "text", "testid", "css"] = Field(
        description="Selector strategy type"
    )
    value: str = Field(description="The selector value (format depends on strategy)")
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence that this selector will work reliably"
    )

    # Role-specific fields (only used when strategy="role")
    role: str | None = Field(default=None, description="ARIA role (button, textbox, link, etc.)")
    name: str | None = Field(default=None, description="Accessible name for role-based selectors")
