"""Codegen-style selector resolution for playback.

Tries selector candidates in priority order until one matches
exactly one element on the page.
"""

from playwright.async_api import Locator, Page

from browser_agents.models import SelectorCandidate, UIEvent


class SelectorResolver:
    """Resolves selector candidates to working Playwright locators.

    Selector priority (same as Playwright Codegen):
    1. role + name - Most resilient
    2. label - Great for form fields
    3. placeholder - Input placeholders
    4. text - Button/link text content
    5. testid - data-testid attributes
    6. css - Last resort fallback

    If all selectors fail, returns None and caller should fall back
    to coordinates.
    """

    def __init__(self, page: Page) -> None:
        """Initialize resolver with a Playwright page.

        Args:
            page: The Playwright page to resolve selectors against.
        """
        self.page = page
        self._last_used_selector: SelectorCandidate | None = None
        self._last_locator: Locator | None = None

    async def resolve(self, event: UIEvent) -> Locator | None:
        """Resolve an event's selectors to a working locator.

        Tries each selector in priority order. Returns the first
        selector that matches exactly one element.

        Args:
            event: The UIEvent containing selectors to try.

        Returns:
            A Playwright Locator if successful, None otherwise.
        """
        if not event.selectors:
            return None

        for candidate in event.selectors:
            try:
                locator = self._to_locator(candidate)
                count = await locator.count()

                if count == 1:
                    # Found exactly one element - success!
                    self._last_used_selector = candidate
                    self._last_locator = locator
                    return locator
                if count > 1:
                    # Multiple matches - try next selector
                    continue
                # count == 0: No match - try next selector
            except Exception:
                # Selector failed (e.g., invalid syntax) - try next
                continue

        # All selectors failed
        self._last_used_selector = None
        self._last_locator = None
        return None

    async def resolve_selectors(
        self, selectors: list[SelectorCandidate]
    ) -> Locator | None:
        """Resolve a list of selector candidates to a working locator.

        Args:
            selectors: List of SelectorCandidate to try in order.

        Returns:
            A Playwright Locator if successful, None otherwise.
        """
        for candidate in selectors:
            try:
                locator = self._to_locator(candidate)
                count = await locator.count()

                if count == 1:
                    self._last_used_selector = candidate
                    self._last_locator = locator
                    return locator
            except Exception:
                continue

        return None

    def _to_locator(self, selector: SelectorCandidate) -> Locator:
        """Convert a SelectorCandidate to a Playwright Locator.

        Args:
            selector: The selector candidate to convert.

        Returns:
            A Playwright Locator.

        Raises:
            ValueError: If the selector strategy is unknown.
        """
        match selector.strategy:
            case "role":
                if selector.role and selector.name:
                    return self.page.get_by_role(selector.role, name=selector.name)  # type: ignore[arg-type]
                if selector.role:
                    return self.page.get_by_role(selector.role)  # type: ignore[arg-type]
                # Fallback to using value as CSS selector
                return self.page.locator(selector.value)

            case "label":
                return self.page.get_by_label(selector.value)

            case "placeholder":
                return self.page.get_by_placeholder(selector.value)

            case "text":
                return self.page.get_by_text(selector.value)

            case "testid":
                return self.page.get_by_test_id(selector.value)

            case "css":
                return self.page.locator(selector.value)

            case _:
                raise ValueError(f"Unknown selector strategy: {selector.strategy}")

    @property
    def last_used_selector(self) -> SelectorCandidate | None:
        """Get the last selector that successfully resolved."""
        return self._last_used_selector

    @property
    def last_locator(self) -> Locator | None:
        """Get the last locator that was successfully created."""
        return self._last_locator
