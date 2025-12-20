"""CDP-based browser event recorder with CLI."""

import asyncio
import json
import signal
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import typer
from playwright.async_api import Page, async_playwright

from browser_agents.models import RecordedEvent, Recording

app = typer.Typer(help="Record browser interactions for automation.")


class BrowserRecorder:
    """Records browser events via CDP."""

    def __init__(self, start_url: str, output_dir: Path) -> None:
        self.start_url = start_url
        self.output_dir = output_dir
        self.session_id = str(uuid.uuid4())[:8]
        self.events: list[RecordedEvent] = []
        self.started_at = datetime.now(UTC)
        self._running = True

    def _add_event(self, event: RecordedEvent) -> None:
        """Add event and print for visibility."""
        self.events.append(event)
        typer.echo(f"  [{event.event_type}] {event.selector or event.url or ''}")

    async def _setup_cdp_listeners(self, page: Page) -> None:
        """Set up CDP event listeners for recording."""
        cdp = await page.context.new_cdp_session(page)

        # Track page navigations
        page.on(
            "framenavigated",
            lambda frame: self._add_event(
                RecordedEvent(
                    timestamp=time.time(),
                    event_type="navigate",
                    url=frame.url,
                )
            )
            if frame == page.main_frame
            else None,
        )

        # Listen for clicks via CDP
        async def on_click(params: dict) -> None:  # type: ignore[type-arg]
            if params.get("type") == "mousePressed" and params.get("button") == "left":
                x, y = int(params.get("x", 0)), int(params.get("y", 0))
                # Try to get selector at click position
                selector = await self._get_selector_at_point(page, x, y)
                self._add_event(
                    RecordedEvent(
                        timestamp=time.time(),
                        event_type="click",
                        selector=selector,
                        x=x,
                        y=y,
                    )
                )

        await cdp.send("Input.enable")
        cdp.on("Input.dispatchMouseEvent", on_click)

        # Listen for keyboard input
        async def on_key(params: dict) -> None:  # type: ignore[type-arg]
            if params.get("type") == "keyDown":
                key = params.get("key", "")
                # Only record actual character input, not modifiers
                if len(key) == 1:
                    self._add_event(
                        RecordedEvent(
                            timestamp=time.time(),
                            event_type="type",
                            value=key,
                        )
                    )

        cdp.on("Input.dispatchKeyEvent", on_key)

    async def _get_selector_at_point(self, page: Page, x: int, y: int) -> str | None:
        """Get a CSS selector for the element at given coordinates."""
        try:
            selector = await page.evaluate(
                """([x, y]) => {
                const el = document.elementFromPoint(x, y);
                if (!el) return null;

                // Prefer data-testid
                if (el.dataset.testid) return `[data-testid="${el.dataset.testid}"]`;

                // Try id
                if (el.id) return `#${el.id}`;

                // Build a selector from tag + classes
                let sel = el.tagName.toLowerCase();
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.trim().split(/\\s+/).slice(0, 2);
                    if (classes.length) sel += '.' + classes.join('.');
                }
                return sel;
            }""",
                [x, y],
            )
            return selector
        except Exception:
            return None

    async def record(self) -> Recording:
        """Start recording and wait for user to stop."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        typer.echo(f"Starting recording session: {self.session_id}")
        typer.echo(f"Navigate to: {self.start_url}")
        typer.echo("Press Ctrl+C to stop recording.\n")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            await self._setup_cdp_listeners(page)
            await page.goto(self.start_url)

            # Wait for Ctrl+C
            try:
                while self._running:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass

            await browser.close()

        return Recording(
            session_id=self.session_id,
            start_url=self.start_url,
            started_at=self.started_at,
            events=self.events,
        )

    def stop(self) -> None:
        """Signal the recorder to stop."""
        self._running = False


def _save_recording(recording: Recording, output_dir: Path) -> Path:
    """Save recording to JSONL file."""
    output_file = output_dir / f"{recording.session_id}.jsonl"
    with output_file.open("w") as f:
        # Write metadata as first line
        f.write(
            json.dumps(
                {
                    "session_id": recording.session_id,
                    "start_url": recording.start_url,
                    "started_at": recording.started_at.isoformat(),
                }
            )
            + "\n"
        )
        # Write events
        for event in recording.events:
            f.write(event.model_dump_json() + "\n")
    return output_file


@app.command()
def record(
    url: str = typer.Argument(..., help="URL to start recording from"),
    output_dir: Path = typer.Option(
        Path("recordings"), "--output", "-o", help="Directory to save recordings"
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
    recording = asyncio.run(recorder.record())

    # Save
    output_file = _save_recording(recording, output_dir)
    typer.echo(f"\nRecorded {len(recording.events)} events")
    typer.echo(f"Saved to: {output_file}")


if __name__ == "__main__":
    app()
