"""Browser event recorder using injected JavaScript listeners."""

import asyncio
import signal
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from playwright.async_api import Page, async_playwright

from browser_agents.models import RecordedEvent, Workflow

app = typer.Typer(help="Record browser interactions for automation.")

# JavaScript injected into pages to capture user events
RECORDER_SCRIPT = """
(() => {
    // Prevent double-injection
    if (window.__recorderInitialized) return;
    window.__recorderInitialized = true;

    // Generate a CSS selector for an element
    function getSelector(el) {
        if (!el || el === document.body || el === document.documentElement) return null;

        // Prefer data-testid
        if (el.dataset && el.dataset.testid) {
            return `[data-testid="${el.dataset.testid}"]`;
        }

        // Try id (if not auto-generated looking)
        if (el.id && !el.id.match(/^[0-9]|^:r[0-9]/)) {
            return `#${el.id}`;
        }

        // Try aria-label
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) {
            return `[aria-label="${ariaLabel}"]`;
        }

        // Try name attribute for form elements
        if (el.name && ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(el.tagName)) {
            return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
        }

        // Build a selector from tag + classes
        let sel = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\\s+/).filter(c => !c.match(/^[0-9]/)).slice(0, 2);
            if (classes.length) sel += '.' + classes.join('.');
        }
        return sel;
    }

    // Click listener (capture phase to get all clicks before they're stopped)
    document.addEventListener('click', (e) => {
        if (window.__recordEvent) {
            window.__recordEvent({
                type: 'click',
                selector: getSelector(e.target),
                x: Math.round(e.clientX),
                y: Math.round(e.clientY)
            });
        }
    }, true);

    // Input listener for form fields (captures the final value)
    document.addEventListener('input', (e) => {
        if (window.__recordEvent && e.target && e.target.tagName) {
            const selector = getSelector(e.target);
            window.__recordEvent({
                type: 'input',
                selector: selector,
                value: e.target.value || ''
            });
        }
    }, true);

    // Scroll listener (debounced to avoid spam)
    let scrollTimeout;
    window.addEventListener('scroll', () => {
        clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => {
            if (window.__recordEvent) {
                window.__recordEvent({
                    type: 'scroll',
                    scrollX: Math.round(window.scrollX),
                    scrollY: Math.round(window.scrollY)
                });
            }
        }, 150);
    }, true);
})();
"""


class BrowserRecorder:
    """Records browser events via injected JavaScript listeners."""

    def __init__(self, start_url: str, output_dir: Path) -> None:
        self.start_url = start_url
        self.output_dir = output_dir
        self.session_id = str(uuid.uuid4())[:8]
        self.events: list[RecordedEvent] = []
        self.started_at = datetime.now(UTC)
        self._running = True
        self._page: Page | None = None
        self._screenshot_dir: Path | None = None
        self._screenshot_count = 0

    async def _take_screenshot(self) -> str | None:
        """Take a screenshot and return the relative path."""
        if not self._page or not self._screenshot_dir:
            return None
        try:
            self._screenshot_count += 1
            filename = f"{self._screenshot_count:04d}.png"
            filepath = self._screenshot_dir / filename
            await self._page.screenshot(path=filepath)
            # Return path relative to workflow dir (screenshots/0001.png)
            return f"screenshots/{filename}"
        except Exception as e:
            typer.echo(f"  [screenshot failed: {e}]", err=True)
            return None

    def _add_event(self, event: RecordedEvent) -> None:
        """Add event and print for visibility."""
        self.events.append(event)
        # Build display string
        detail = event.selector or event.url or event.value or ""
        if len(detail) > 50:
            detail = detail[:47] + "..."
        screenshot_indicator = " [+screenshot]" if event.screenshot_path else ""
        typer.echo(f"  [{event.event_type}] {detail}{screenshot_indicator}")

    async def _handle_page_event(self, event_data: dict[str, Any]) -> None:
        """Handle events received from injected page script."""
        event_type = event_data.get("type")

        if event_type == "click":
            # Take screenshot after click (captures resulting state)
            # Small delay to let any animations/transitions settle
            await asyncio.sleep(0.1)
            screenshot_path = await self._take_screenshot()
            self._add_event(
                RecordedEvent(
                    timestamp=time.time(),
                    event_type="click",
                    selector=event_data.get("selector"),
                    x=event_data.get("x"),
                    y=event_data.get("y"),
                    screenshot_path=screenshot_path,
                )
            )
        elif event_type == "input":
            # No screenshot for individual keystrokes (too many)
            self._add_event(
                RecordedEvent(
                    timestamp=time.time(),
                    event_type="type",
                    selector=event_data.get("selector"),
                    value=event_data.get("value"),
                )
            )
        elif event_type == "scroll":
            self._add_event(
                RecordedEvent(
                    timestamp=time.time(),
                    event_type="scroll",
                    scroll_x=event_data.get("scrollX"),
                    scroll_y=event_data.get("scrollY"),
                )
            )

    async def _setup_event_capture(self, page: Page) -> None:
        """Set up event capture via injected JavaScript."""
        self._page = page

        # Expose callback to receive events from page JavaScript
        await page.expose_function("__recordEvent", self._handle_page_event)

        # Inject event listeners - runs automatically on every navigation
        await page.add_init_script(RECORDER_SCRIPT)

        # Also run immediately for the current page
        try:
            await page.evaluate(RECORDER_SCRIPT)
        except Exception:
            # CSP may block inline scripts on some sites - that's OK
            # add_init_script will work on subsequent navigations
            pass

        # Track page navigations via Playwright's built-in event
        async def on_navigate(frame: Any) -> None:
            if frame == page.main_frame:
                # Small delay to let page settle after navigation
                await asyncio.sleep(0.3)
                screenshot_path = await self._take_screenshot()
                self._add_event(
                    RecordedEvent(
                        timestamp=time.time(),
                        event_type="navigate",
                        url=frame.url,
                        screenshot_path=screenshot_path,
                    )
                )

        page.on("framenavigated", lambda f: asyncio.create_task(on_navigate(f)))

    async def record(self) -> Workflow:
        """Start recording and wait for user to stop."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create screenshot directory for this session
        self._screenshot_dir = self.output_dir / self.session_id / "screenshots"
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

        typer.echo(f"Starting recording session: {self.session_id}")
        typer.echo(f"Navigate to: {self.start_url}")
        typer.echo(f"Screenshots: {self._screenshot_dir}")
        typer.echo("Close the browser or press Ctrl+C to stop recording.\n")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            await self._setup_event_capture(page)
            await page.goto(self.start_url)

            # Set up page close detection
            page_closed = asyncio.Event()
            page.on("close", lambda: page_closed.set())

            # Wait for Ctrl+C or page close
            try:
                while self._running and not page_closed.is_set():
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass

            # Close browser gracefully (may already be closed if user closed window)
            try:
                await browser.close()
            except Exception:
                pass  # Browser already closed or connection lost

        return Workflow(
            id=self.session_id,
            source_url=self.start_url,
            created_at=self.started_at,
            events=self.events,
        )

    def stop(self) -> None:
        """Signal the recorder to stop."""
        self._running = False


def _save_workflow(workflow: Workflow, output_dir: Path) -> Path:
    """Save workflow to JSON file inside session folder."""
    # Save in session folder alongside screenshots
    session_dir = output_dir / workflow.id
    session_dir.mkdir(parents=True, exist_ok=True)
    output_file = session_dir / "workflow.json"
    with output_file.open("w", encoding="utf-8") as f:
        f.write(workflow.model_dump_json(indent=2))
    return output_file


@app.command()
def record(
    url: str = typer.Argument(..., help="URL to start recording from"),
    output_dir: Path = typer.Option(
        Path("workflows"), "--output", "-o", help="Directory to save workflows"
    ),
) -> None:
    """Start recording browser interactions."""
    recorder = BrowserRecorder(url, output_dir)

    # Handle Ctrl+C gracefully
    def handle_sigint(sig: int, frame: object) -> None:
        typer.echo("\nStopping recording...")
        recorder.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    # Run the recorder
    workflow = asyncio.run(recorder.record())

    # Save
    output_file = _save_workflow(workflow, output_dir)
    typer.echo(f"\nRecorded {len(workflow.events)} events")
    typer.echo(f"Saved to: {output_file}")


if __name__ == "__main__":
    app()
