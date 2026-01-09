"""Session replay executor.

Replays recorded UIEvents using Codegen-style selector resolution.
Falls back to coordinates when all selectors fail.
"""

import asyncio
from collections.abc import Callable

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from browser_agents.models import RecordingSession, UIEvent, UIEventType

from .selector_resolver import SelectorResolver

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
    """Executes recorded sessions with Codegen-style selector resolution.

    Features:
    - Tries selectors in priority order (role → label → placeholder → text → testid → css)
    - Falls back to coordinates when all selectors fail
    - Configurable delay between events
    - Progress callback support
    - Configurable navigation wait strategy
    """

    def __init__(
        self,
        page: Page,
        delay_ms: int = DEFAULT_DELAY_MS,
        on_event: Callable[[UIEvent, int, int], None] | None = None,
        wait_until: str = "domcontentloaded",
    ) -> None:
        """Initialize the executor.

        Args:
            page: Playwright page to execute on.
            delay_ms: Delay between events in milliseconds.
            on_event: Callback(event, index, total) called before each event.
            wait_until: Navigation wait strategy ("load", "domcontentloaded",
                "networkidle", "commit"). Default "domcontentloaded".
        """
        self.page = page
        self.delay_ms = delay_ms
        self.on_event = on_event
        self.wait_until = wait_until
        self.resolver = SelectorResolver(page)

    async def replay_session(self, session: RecordingSession) -> None:
        """Replay all events from a recording session.

        Args:
            session: The RecordingSession to replay.

        Raises:
            PlaybackError: If an event fails to execute.
        """
        events = session.events
        total = len(events)

        for i, event in enumerate(events):
            if self.on_event:
                self.on_event(event, i, total)

            await self._replay_event(event)

            if self.delay_ms > 0 and i < total - 1:
                await asyncio.sleep(self.delay_ms / 1000)

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
        locator = await self.resolver.resolve(event)
        if locator:
            await locator.click(timeout=ELEMENT_TIMEOUT)
        elif event.x is not None and event.y is not None:
            await self.page.mouse.click(event.x, event.y)
        else:
            raise PlaybackError("No selector or coordinates for click", event)

    async def _handle_double_click(self, event: UIEvent) -> None:
        """Handle double-click event."""
        locator = await self.resolver.resolve(event)
        if locator:
            await locator.dblclick(timeout=ELEMENT_TIMEOUT)
        elif event.x is not None and event.y is not None:
            await self.page.mouse.dblclick(event.x, event.y)
        else:
            raise PlaybackError("No selector or coordinates for double-click", event)

    async def _handle_right_click(self, event: UIEvent) -> None:
        """Handle right-click event."""
        locator = await self.resolver.resolve(event)
        if locator:
            await locator.click(button="right", timeout=ELEMENT_TIMEOUT)
        elif event.x is not None and event.y is not None:
            await self.page.mouse.click(event.x, event.y, button="right")
        else:
            raise PlaybackError("No selector or coordinates for right-click", event)

    async def _handle_type(self, event: UIEvent) -> None:
        """Handle type event."""
        if event.value is None:
            return  # Nothing to type

        locator = await self.resolver.resolve(event)
        if locator:
            await locator.fill(event.value, timeout=ELEMENT_TIMEOUT)
        else:
            raise PlaybackError("No selector for type event", event)

    async def _handle_clear(self, event: UIEvent) -> None:
        """Handle clear event."""
        locator = await self.resolver.resolve(event)
        if locator:
            await locator.clear(timeout=ELEMENT_TIMEOUT)
        else:
            raise PlaybackError("No selector for clear event", event)

    async def _handle_select_option(self, event: UIEvent) -> None:
        """Handle select option event."""
        if event.value is None:
            return

        locator = await self.resolver.resolve(event)
        if locator:
            # Try to select by text first, then by value
            try:
                await locator.select_option(label=event.value, timeout=ELEMENT_TIMEOUT)
            except Exception:
                await locator.select_option(value=event.value, timeout=ELEMENT_TIMEOUT)
        else:
            raise PlaybackError("No selector for select_option event", event)

    async def _handle_check(self, event: UIEvent) -> None:
        """Handle check event."""
        locator = await self.resolver.resolve(event)
        if locator:
            await locator.check(timeout=ELEMENT_TIMEOUT)
        else:
            raise PlaybackError("No selector for check event", event)

    async def _handle_uncheck(self, event: UIEvent) -> None:
        """Handle uncheck event."""
        locator = await self.resolver.resolve(event)
        if locator:
            await locator.uncheck(timeout=ELEMENT_TIMEOUT)
        else:
            raise PlaybackError("No selector for uncheck event", event)

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
