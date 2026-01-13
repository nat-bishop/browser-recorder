"""Session replay executor.

Replays recorded UIEvents using Playwright selectors.
Fails explicitly if selector doesn't match - no fallback to coordinates.
"""

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from browser_agents.models import UIEvent, UIEventType

# Timeout for element operations (ms)
ELEMENT_TIMEOUT = 5000

# Default delay between events (ms)
DEFAULT_DELAY_MS = 100


class PlaybackError(Exception):
    """Error during session playback."""

    def __init__(self, message: str, event: UIEvent | None = None) -> None:
        super().__init__(message)
        self.event = event


class SessionExecutor:
    """Executes recorded sessions using Playwright selectors.

    Features:
    - Uses Playwright's selector resolution directly
    - Fails explicitly if selector doesn't match
    - Configurable delay between events
    - Configurable navigation wait strategy
    """

    def __init__(
        self,
        page: Page,
        delay_ms: int = DEFAULT_DELAY_MS,
        wait_until: str = "domcontentloaded",
    ) -> None:
        """Initialize the executor.

        Args:
            page: Playwright page to execute on.
            delay_ms: Delay between events in milliseconds.
            wait_until: Navigation wait strategy ("load", "domcontentloaded",
                "networkidle", "commit"). Default "domcontentloaded".
        """
        self.page = page
        self.delay_ms = delay_ms
        self.wait_until = wait_until

    async def replay_event(self, event: UIEvent) -> None:
        """Replay a single event.

        Args:
            event: The UIEvent to replay.

        Raises:
            PlaybackError: If the event fails to execute.
        """
        await self._replay_event(event)

    async def _replay_event(self, event: UIEvent) -> None:
        """Internal method to replay a single event."""
        try:
            match event.event_type:
                case UIEventType.CLICK:
                    await self._handle_click(event)

                case UIEventType.DOUBLE_CLICK:
                    await self._handle_double_click(event)

                case UIEventType.RIGHT_CLICK:
                    await self._handle_right_click(event)

                case UIEventType.TYPE:
                    await self._handle_type(event)

                case UIEventType.CLEAR:
                    await self._handle_clear(event)

                case UIEventType.SELECT_OPTION:
                    await self._handle_select_option(event)

                case UIEventType.CHECK:
                    await self._handle_check(event)

                case UIEventType.UNCHECK:
                    await self._handle_uncheck(event)

                case UIEventType.SCROLL:
                    await self._handle_scroll(event)

                case UIEventType.NAVIGATE:
                    await self._handle_navigate(event)

                case UIEventType.KEY_PRESS:
                    await self._handle_key_press(event)

                case _:
                    raise PlaybackError(
                        f"Unknown event type: {event.event_type}", event
                    )

        except PlaywrightTimeoutError as e:
            raise PlaybackError(f"Timeout: {e}", event) from e
        except Exception as e:
            if isinstance(e, PlaybackError):
                raise
            raise PlaybackError(f"Failed to execute event: {e}", event) from e

    async def _handle_click(self, event: UIEvent) -> None:
        """Handle click event."""
        if not event.selector:
            raise PlaybackError("No selector for click event", event)
        locator = self.page.locator(event.selector)
        await locator.click(timeout=ELEMENT_TIMEOUT)

    async def _handle_double_click(self, event: UIEvent) -> None:
        """Handle double-click event."""
        if not event.selector:
            raise PlaybackError("No selector for double-click event", event)
        locator = self.page.locator(event.selector)
        await locator.dblclick(timeout=ELEMENT_TIMEOUT)

    async def _handle_right_click(self, event: UIEvent) -> None:
        """Handle right-click event."""
        if not event.selector:
            raise PlaybackError("No selector for right-click event", event)
        locator = self.page.locator(event.selector)
        await locator.click(button="right", timeout=ELEMENT_TIMEOUT)

    async def _handle_type(self, event: UIEvent) -> None:
        """Handle type event."""
        if event.value is None:
            return  # Nothing to type
        if not event.selector:
            raise PlaybackError("No selector for type event", event)
        locator = self.page.locator(event.selector)
        await locator.fill(event.value, timeout=ELEMENT_TIMEOUT)

    async def _handle_clear(self, event: UIEvent) -> None:
        """Handle clear event."""
        if not event.selector:
            raise PlaybackError("No selector for clear event", event)
        locator = self.page.locator(event.selector)
        await locator.clear(timeout=ELEMENT_TIMEOUT)

    async def _handle_select_option(self, event: UIEvent) -> None:
        """Handle select option event."""
        if event.value is None:
            return
        if not event.selector:
            raise PlaybackError("No selector for select_option event", event)
        locator = self.page.locator(event.selector)
        # Try to select by text first, then by value
        try:
            await locator.select_option(label=event.value, timeout=ELEMENT_TIMEOUT)
        except Exception:
            await locator.select_option(value=event.value, timeout=ELEMENT_TIMEOUT)

    async def _handle_check(self, event: UIEvent) -> None:
        """Handle check event."""
        if not event.selector:
            raise PlaybackError("No selector for check event", event)
        locator = self.page.locator(event.selector)
        await locator.check(timeout=ELEMENT_TIMEOUT)

    async def _handle_uncheck(self, event: UIEvent) -> None:
        """Handle uncheck event."""
        if not event.selector:
            raise PlaybackError("No selector for uncheck event", event)
        locator = self.page.locator(event.selector)
        await locator.uncheck(timeout=ELEMENT_TIMEOUT)

    async def _handle_scroll(self, event: UIEvent) -> None:
        """Handle scroll event."""
        if event.scroll_x is not None and event.scroll_y is not None:
            await self.page.evaluate(
                f"window.scrollTo({event.scroll_x}, {event.scroll_y})"
            )
        elif event.scroll_y is not None:
            await self.page.evaluate(f"window.scrollTo(0, {event.scroll_y})")

    async def _handle_navigate(self, event: UIEvent) -> None:
        """Handle navigate event."""
        if event.url:
            await self.page.goto(event.url, wait_until=self.wait_until)  # type: ignore[arg-type]

    async def _handle_key_press(self, event: UIEvent) -> None:
        """Handle key press event."""
        if event.key:
            await self.page.keyboard.press(event.key)
