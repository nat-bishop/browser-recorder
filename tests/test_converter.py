"""Tests for the converter module.

These tests mock the LLM to test converter logic without making API calls.
For integration tests with real LLM, see test_converter_integration.py.
"""

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from browser_agents.converter import (
    convert_workflow_to_action,
    load_workflow,
)
from browser_agents.models import ActionDefinition

if TYPE_CHECKING:
    from browser_agents.models import Workflow


class TestLoadWorkflow:
    """Tests for load_workflow function."""

    def test_loads_valid_workflow(self, sample_workflow: Path) -> None:
        """Valid JSON file is loaded correctly."""
        workflow = load_workflow(sample_workflow)

        assert workflow.id == "test123"
        assert workflow.source_url == "https://example.com"
        assert len(workflow.events) == 2

    def test_empty_file_raises_error(self, workflows_dir: Path) -> None:
        """Empty file raises ValueError."""
        empty_file = workflows_dir / "empty.json"
        empty_file.write_text("")

        with pytest.raises(ValueError, match="empty"):
            load_workflow(empty_file)

    def test_file_not_found_raises_error(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_workflow(tmp_path / "nonexistent.json")

    def test_invalid_json_raises_error(self, invalid_workflow: Path) -> None:
        """Invalid JSON raises exception."""
        with pytest.raises(Exception):  # json.JSONDecodeError or ValidationError
            load_workflow(invalid_workflow)


class TestConvertWorkflowToAction:
    """Tests for convert_workflow_to_action function."""

    async def test_returns_action_definition_on_success(
        self,
        sample_workflow_model: "Workflow",
        mock_llm: AsyncMock,
        mock_action_definition: ActionDefinition,
    ) -> None:
        """Successful conversion returns ActionDefinition."""
        with patch(
            "browser_agents.converter.get_structured_llm",
            return_value=mock_llm,
        ):
            result = await convert_workflow_to_action(
                sample_workflow_model, description="Login to the site"
            )

        assert isinstance(result, ActionDefinition)
        assert result.name == "login_user"
        mock_llm.ainvoke.assert_called_once()

    async def test_returns_error_string_on_llm_failure(
        self,
        sample_workflow_model: "Workflow",
    ) -> None:
        """LLM failure returns error string."""
        from unittest.mock import Mock

        mock = Mock()
        mock.ainvoke = AsyncMock(side_effect=ConnectionError("Connection timeout"))
        mock.with_retry.return_value = mock

        with patch(
            "browser_agents.converter.get_structured_llm",
            return_value=mock,
        ):
            result = await convert_workflow_to_action(
                sample_workflow_model, description="Login to the site"
            )

        assert isinstance(result, str)
        assert "failed" in result.lower() or "connection" in result.lower()

    async def test_rejects_short_workflow(
        self,
        mock_llm: AsyncMock,
    ) -> None:
        """Workflow with < 2 events is rejected."""
        from datetime import UTC, datetime

        from browser_agents.models import RecordedEvent, Workflow

        short_workflow = Workflow(
            id="short",
            source_url="https://example.com",
            created_at=datetime.now(UTC),
            events=[
                RecordedEvent(timestamp=1.0, event_type="click", selector="#btn"),
            ],
        )

        with patch(
            "browser_agents.converter.get_structured_llm",
            return_value=mock_llm,
        ):
            result = await convert_workflow_to_action(short_workflow, description="Click a button")

        assert isinstance(result, str)
        assert "too short" in result.lower()
        mock_llm.ainvoke.assert_not_called()

    async def test_returns_error_on_empty_llm_response(
        self,
        sample_workflow_model: "Workflow",
    ) -> None:
        """Empty LLM response returns error string."""
        from unittest.mock import Mock

        mock = Mock()
        mock.ainvoke = AsyncMock(return_value=None)
        mock.with_retry.return_value = mock

        with patch(
            "browser_agents.converter.get_structured_llm",
            return_value=mock,
        ):
            result = await convert_workflow_to_action(
                sample_workflow_model, description="Login to the site"
            )

        assert isinstance(result, str)
        assert "empty" in result.lower()

    async def test_returns_error_on_incomplete_action(
        self,
        sample_workflow_model: "Workflow",
    ) -> None:
        """ActionDefinition without name or steps returns error."""
        from unittest.mock import Mock

        from browser_agents.models import ActionDefinition

        incomplete = ActionDefinition(
            name="",  # Empty name
            description="test",
            parameters=[],
            steps=[],  # Empty steps
            domains=["example.com"],
        )

        mock = Mock()
        mock.ainvoke = AsyncMock(return_value=incomplete)
        mock.with_retry.return_value = mock

        with patch(
            "browser_agents.converter.get_structured_llm",
            return_value=mock,
        ):
            result = await convert_workflow_to_action(
                sample_workflow_model, description="Login to the site"
            )

        assert isinstance(result, str)
        assert "incomplete" in result.lower()


class TestConvertWorkflowIntegration:
    """Integration tests that would call real LLM.

    These are marked @slow and skipped by default.
    Run with: pytest -m slow
    """

    @pytest.mark.slow
    async def test_real_conversion_with_ollama(self) -> None:
        """Test actual LLM conversion (requires Ollama running)."""
        # This test is skipped by default
        # It requires:
        # 1. Ollama running at localhost:11434
        # 2. gpt-oss:120b model pulled
        pytest.skip("Manual integration test - requires Ollama")
