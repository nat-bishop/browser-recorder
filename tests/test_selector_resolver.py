"""Unit tests for SelectorResolver.

These tests mock Playwright page/locators to test selector resolution logic
without requiring a browser.

Run with: uv run pytest tests/test_selector_resolver.py -v
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from browser_agents.models import SelectorCandidate, UIEvent, UIEventType
from browser_agents.playback.selector_resolver import SelectorResolver


@pytest.fixture
def mock_page() -> MagicMock:
    """Create a mock Playwright page."""
    page = MagicMock()
    # Configure async methods to return MagicMock locators
    page.get_by_role = MagicMock()
    page.get_by_label = MagicMock()
    page.get_by_placeholder = MagicMock()
    page.get_by_text = MagicMock()
    page.get_by_test_id = MagicMock()
    page.locator = MagicMock()
    return page


@pytest.fixture
def resolver(mock_page: MagicMock) -> SelectorResolver:
    """Create a SelectorResolver with a mock page."""
    return SelectorResolver(mock_page)


def make_mock_locator(count: int = 1) -> MagicMock:
    """Create a mock locator that returns a specific count."""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=count)
    return locator


def make_event(selectors: list[SelectorCandidate]) -> UIEvent:
    """Create a UIEvent with the given selectors."""
    return UIEvent(
        id="test_event",
        timestamp=datetime.now(UTC),
        relative_time_ms=0,
        event_type=UIEventType.CLICK,
        url="https://example.com",
        selectors=selectors,
    )


class TestToLocator:
    """Tests for _to_locator method."""

    def test_role_selector_with_name(self, resolver: SelectorResolver) -> None:
        """Role selector with name uses get_by_role(role, name=name)."""
        selector = SelectorCandidate(
            strategy="role",
            value='role=button[name="Submit"]',
            confidence="high",
            role="button",
            name="Submit",
        )
        resolver._to_locator(selector)
        resolver.page.get_by_role.assert_called_once_with("button", name="Submit")

    def test_role_selector_without_name(self, resolver: SelectorResolver) -> None:
        """Role selector without name uses get_by_role(role)."""
        selector = SelectorCandidate(
            strategy="role",
            value="role=button",
            confidence="high",
            role="button",
        )
        resolver._to_locator(selector)
        resolver.page.get_by_role.assert_called_once_with("button")

    def test_role_selector_fallback_to_css(self, resolver: SelectorResolver) -> None:
        """Role selector without role field falls back to locator(value)."""
        selector = SelectorCandidate(
            strategy="role",
            value="role=button[name='Submit']",
            confidence="high",
        )
        resolver._to_locator(selector)
        resolver.page.locator.assert_called_once_with("role=button[name='Submit']")

    def test_label_selector(self, resolver: SelectorResolver) -> None:
        """Label selector uses get_by_label."""
        selector = SelectorCandidate(
            strategy="label",
            value="Email Address",
            confidence="high",
        )
        resolver._to_locator(selector)
        resolver.page.get_by_label.assert_called_once_with("Email Address")

    def test_placeholder_selector(self, resolver: SelectorResolver) -> None:
        """Placeholder selector uses get_by_placeholder."""
        selector = SelectorCandidate(
            strategy="placeholder",
            value="Enter your email",
            confidence="medium",
        )
        resolver._to_locator(selector)
        resolver.page.get_by_placeholder.assert_called_once_with("Enter your email")

    def test_text_selector(self, resolver: SelectorResolver) -> None:
        """Text selector uses get_by_text."""
        selector = SelectorCandidate(
            strategy="text",
            value="Sign In",
            confidence="medium",
        )
        resolver._to_locator(selector)
        resolver.page.get_by_text.assert_called_once_with("Sign In")

    def test_testid_selector(self, resolver: SelectorResolver) -> None:
        """Testid selector uses get_by_test_id."""
        selector = SelectorCandidate(
            strategy="testid",
            value="submit-button",
            confidence="high",
        )
        resolver._to_locator(selector)
        resolver.page.get_by_test_id.assert_called_once_with("submit-button")

    def test_css_selector(self, resolver: SelectorResolver) -> None:
        """CSS selector uses locator."""
        selector = SelectorCandidate(
            strategy="css",
            value="#submit-btn",
            confidence="low",
        )
        resolver._to_locator(selector)
        resolver.page.locator.assert_called_once_with("#submit-btn")

    def test_unknown_strategy_raises(self, resolver: SelectorResolver) -> None:
        """Unknown strategy raises ValueError."""
        # Create mock selector to bypass Pydantic validation
        selector = MagicMock()
        selector.strategy = "unknown"
        selector.value = "test"

        with pytest.raises(ValueError, match="Unknown selector strategy"):
            resolver._to_locator(selector)


class TestResolve:
    """Tests for resolve method."""

    @pytest.mark.asyncio
    async def test_returns_first_matching_selector(
        self, resolver: SelectorResolver
    ) -> None:
        """Returns locator from first selector that matches exactly one element."""
        # First selector matches one element
        first_locator = make_mock_locator(count=1)
        resolver.page.get_by_role.return_value = first_locator

        event = make_event(
            [
                SelectorCandidate(
                    strategy="role",
                    value='role=button[name="Submit"]',
                    confidence="high",
                    role="button",
                    name="Submit",
                ),
                SelectorCandidate(
                    strategy="css",
                    value="#submit-btn",
                    confidence="low",
                ),
            ]
        )

        result = await resolver.resolve(event)

        assert result == first_locator
        # Should not have tried CSS selector
        resolver.page.locator.assert_not_called()

    @pytest.mark.asyncio
    async def test_tries_next_selector_when_no_match(
        self, resolver: SelectorResolver
    ) -> None:
        """Tries next selector when current one matches zero elements."""
        # First selector matches zero elements
        first_locator = make_mock_locator(count=0)
        resolver.page.get_by_role.return_value = first_locator

        # Second selector matches one element
        second_locator = make_mock_locator(count=1)
        resolver.page.locator.return_value = second_locator

        event = make_event(
            [
                SelectorCandidate(
                    strategy="role",
                    value='role=button[name="Submit"]',
                    confidence="high",
                    role="button",
                    name="Submit",
                ),
                SelectorCandidate(
                    strategy="css",
                    value="#submit-btn",
                    confidence="low",
                ),
            ]
        )

        result = await resolver.resolve(event)

        assert result == second_locator
        # Should have tried both selectors
        resolver.page.get_by_role.assert_called_once()
        resolver.page.locator.assert_called_once()

    @pytest.mark.asyncio
    async def test_tries_next_selector_when_multiple_matches(
        self, resolver: SelectorResolver
    ) -> None:
        """Tries next selector when current one matches multiple elements."""
        # First selector matches multiple elements
        first_locator = make_mock_locator(count=3)
        resolver.page.get_by_text.return_value = first_locator

        # Second selector matches one element
        second_locator = make_mock_locator(count=1)
        resolver.page.get_by_test_id.return_value = second_locator

        event = make_event(
            [
                SelectorCandidate(
                    strategy="text",
                    value="Submit",
                    confidence="medium",
                ),
                SelectorCandidate(
                    strategy="testid",
                    value="submit-btn",
                    confidence="high",
                ),
            ]
        )

        result = await resolver.resolve(event)

        assert result == second_locator

    @pytest.mark.asyncio
    async def test_returns_none_when_no_selectors_match(
        self, resolver: SelectorResolver
    ) -> None:
        """Returns None when all selectors fail to match."""
        # All selectors match zero elements
        zero_locator = make_mock_locator(count=0)
        resolver.page.get_by_role.return_value = zero_locator
        resolver.page.locator.return_value = zero_locator

        event = make_event(
            [
                SelectorCandidate(
                    strategy="role",
                    value='role=button[name="Submit"]',
                    confidence="high",
                    role="button",
                    name="Submit",
                ),
                SelectorCandidate(
                    strategy="css",
                    value="#submit-btn",
                    confidence="low",
                ),
            ]
        )

        result = await resolver.resolve(event)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_selectors(
        self, resolver: SelectorResolver
    ) -> None:
        """Returns None when event has no selectors."""
        event = make_event([])
        result = await resolver.resolve(event)
        assert result is None

    @pytest.mark.asyncio
    async def test_continues_on_selector_exception(
        self, resolver: SelectorResolver
    ) -> None:
        """Continues to next selector when current one raises exception."""
        # First selector throws exception
        resolver.page.get_by_label.side_effect = Exception("Invalid selector")

        # Second selector matches
        second_locator = make_mock_locator(count=1)
        resolver.page.locator.return_value = second_locator

        event = make_event(
            [
                SelectorCandidate(
                    strategy="label",
                    value="Invalid",
                    confidence="high",
                ),
                SelectorCandidate(
                    strategy="css",
                    value="#btn",
                    confidence="low",
                ),
            ]
        )

        result = await resolver.resolve(event)

        assert result == second_locator


class TestSelectorPriority:
    """Tests verifying selector priority behavior."""

    @pytest.mark.asyncio
    async def test_role_preferred_over_css(self, resolver: SelectorResolver) -> None:
        """Role selector is tried before CSS selector."""
        role_locator = make_mock_locator(count=1)
        css_locator = make_mock_locator(count=1)

        resolver.page.get_by_role.return_value = role_locator
        resolver.page.locator.return_value = css_locator

        event = make_event(
            [
                SelectorCandidate(
                    strategy="role",
                    value='role=button[name="Submit"]',
                    confidence="high",
                    role="button",
                    name="Submit",
                ),
                SelectorCandidate(
                    strategy="css",
                    value="#submit-btn",
                    confidence="low",
                ),
            ]
        )

        result = await resolver.resolve(event)

        # Should use role selector (first one that matches)
        assert result == role_locator
        resolver.page.get_by_role.assert_called_once()
        # CSS should not be tried since role matched
        resolver.page.locator.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_strategies_in_priority_order(self) -> None:
        """All selector strategies work when they're the first match."""
        strategies = [
            ("role", "get_by_role", {"role": "button", "name": "Test"}),
            ("label", "get_by_label", {}),
            ("placeholder", "get_by_placeholder", {}),
            ("text", "get_by_text", {}),
            ("testid", "get_by_test_id", {}),
            ("css", "locator", {}),
        ]

        for strategy, method_name, extra_fields in strategies:
            # Reset mock
            mock_page = MagicMock()
            res = SelectorResolver(mock_page)

            # Set up locator that matches
            locator = make_mock_locator(count=1)
            getattr(mock_page, method_name).return_value = locator

            selector = SelectorCandidate(
                strategy=strategy,  # type: ignore[arg-type]
                value="test-value",
                confidence="high",
                **extra_fields,
            )
            event = make_event([selector])

            result = await res.resolve(event)

            assert result == locator, f"Strategy {strategy} should resolve"
