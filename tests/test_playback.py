"""Tests for playback module functions.

These tests verify parameter substitution and action step replay logic.
Run with: uv run pytest tests/test_playback.py -v
"""

from browser_agents.models import ActionStep, StepAction
from browser_agents.playback import substitute_params


class TestSubstituteParams:
    """Tests for substitute_params function."""

    def test_substitutes_single_param(self) -> None:
        """Single parameter placeholder is replaced."""
        step = ActionStep(
            action=StepAction.type,
            target="#email",
            value="{email}",
            description="Enter email",
        )
        params = {"email": "test@example.com"}

        result = substitute_params(step, params)

        assert result.value == "test@example.com"
        assert result.target == "#email"  # Unchanged

    def test_substitutes_multiple_params(self) -> None:
        """Multiple parameter placeholders are replaced."""
        step = ActionStep(
            action=StepAction.type,
            target="#greeting",
            value="Hello {first_name} {last_name}!",
            description="Enter greeting",
        )
        params = {"first_name": "John", "last_name": "Doe"}

        result = substitute_params(step, params)

        assert result.value == "Hello John Doe!"

    def test_no_substitution_when_no_placeholders(self) -> None:
        """Step without placeholders is unchanged."""
        step = ActionStep(
            action=StepAction.type,
            target="#static",
            value="static text",
            description="Enter static text",
        )
        params = {"unused": "value"}

        result = substitute_params(step, params)

        assert result.value == "static text"

    def test_no_substitution_when_no_params(self) -> None:
        """Step is unchanged when params is empty."""
        step = ActionStep(
            action=StepAction.type,
            target="#field",
            value="{placeholder}",
            description="Enter value",
        )
        params: dict[str, str] = {}

        result = substitute_params(step, params)

        assert result.value == "{placeholder}"

    def test_no_substitution_when_value_is_none(self) -> None:
        """Step with None value is unchanged."""
        step = ActionStep(
            action=StepAction.click,
            target="#button",
            value=None,
            description="Click button",
        )
        params = {"email": "test@example.com"}

        result = substitute_params(step, params)

        assert result.value is None

    def test_returns_copy_not_mutating_original(self) -> None:
        """Substitution returns a copy, doesn't mutate original."""
        step = ActionStep(
            action=StepAction.type,
            target="#email",
            value="{email}",
            description="Enter email",
        )
        params = {"email": "test@example.com"}

        result = substitute_params(step, params)

        assert result.value == "test@example.com"
        assert step.value == "{email}"  # Original unchanged

    def test_partial_substitution(self) -> None:
        """Only matching placeholders are replaced."""
        step = ActionStep(
            action=StepAction.type,
            target="#field",
            value="{known} and {unknown}",
            description="Mixed params",
        )
        params = {"known": "replaced"}

        result = substitute_params(step, params)

        assert result.value == "replaced and {unknown}"

    def test_preserves_other_fields(self) -> None:
        """Other step fields are preserved after substitution."""
        step = ActionStep(
            action=StepAction.type,
            target="#email",
            value="{email}",
            description="Enter email",
            fallback_coords=[100, 200],
            fallback_text="Email field",
        )
        params = {"email": "test@example.com"}

        result = substitute_params(step, params)

        assert result.action == StepAction.type
        assert result.target == "#email"
        assert result.description == "Enter email"
        assert result.fallback_coords == [100, 200]
        assert result.fallback_text == "Email field"
