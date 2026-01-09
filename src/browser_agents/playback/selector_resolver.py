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

    Supports iframe context via UIEvent.frame_type and frame_src.
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

        Handles iframe context when event.frame_type == "iframe".

        Args:
            event: The UIEvent containing selectors to try.

        Returns:
            A Playwright Locator if successful, None otherwise.
        """
        if not event.selectors:
            return None

        # Get the appropriate context (main page or iframe)
        context = self._get_frame_context(event)

        for candidate in event.selectors:
            try:
                locator = self._to_locator(candidate, context)
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

    def _get_frame_context(self, event: UIEvent) -> Page:
        """Get the appropriate frame context for an event.

        If the event occurred in an iframe, try to find that frame.
        Falls back to main page if frame not found.

        Args:
            event: The UIEvent to get context for.

        Returns:
            The Page or Frame to use for locator resolution.
        """
        if event.frame_type == "iframe" and event.frame_src:
            # Try to find the iframe by its src URL
            frame = self.page.frame(url=event.frame_src)
            if frame:
                return frame  # type: ignore[return-value]

            # Try partial URL match (some iframes have dynamic params)
            for frame in self.page.frames:
                if event.frame_src in (frame.url or ""):
                    return frame  # type: ignore[return-value]

        return self.page

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

        # Reset tracking on failure (match resolve() behavior)
        self._last_used_selector = None
        self._last_locator = None
        return None

    def _to_locator(
        self, selector: SelectorCandidate, context: Page | None = None
    ) -> Locator:
        """Convert a SelectorCandidate to a Playwright Locator.

        Args:
            selector: The selector candidate to convert.
            context: The Page or Frame to use (defaults to self.page).

        Returns:
            A Playwright Locator.

        Raises:
            ValueError: If the selector strategy is unknown.
        """
        ctx = context or self.page

        match selector.strategy:
            case "role":
                if selector.role and selector.name:
                    return ctx.get_by_role(selector.role, name=selector.name)  # type: ignore[arg-type]
                if selector.role:
                    return ctx.get_by_role(selector.role)  # type: ignore[arg-type]
                # Fallback to using value as CSS selector
                return ctx.locator(selector.value)

            case "label":
                return ctx.get_by_label(selector.value)

            case "placeholder":
                return ctx.get_by_placeholder(selector.value)

            case "text":
                return ctx.get_by_text(selector.value)

            case "testid":
                return ctx.get_by_test_id(selector.value)

            case "css":
                return ctx.locator(selector.value)

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
