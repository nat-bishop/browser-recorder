"""Replay recorded browser sessions."""

import asyncio
import json
from pathlib import Path

import typer
from playwright.async_api import Page, async_playwright

from browser_agents.models import RecordedEvent

app = typer.Typer(help="Replay recorded browser sessions.")


async def _replay_event(page: Page, event: RecordedEvent) -> bool:
    """Replay a single event. Returns True on success."""
    try:
        if event.event_type == "navigate":
            if event.url:
                await page.goto(event.url)
            return True

        elif event.event_type == "click":
            if event.selector:
                await page.click(event.selector)
            elif event.x is not None and event.y is not None:
                await page.mouse.click(event.x, event.y)
            return True

        elif event.event_type == "type":
            if event.value:
                await page.keyboard.type(event.value)
            return True

        elif event.event_type == "scroll":
            if event.scroll_x is not None and event.scroll_y is not None:
                await page.evaluate(f"window.scrollTo({event.scroll_x}, {event.scroll_y})")
            return True

        elif event.event_type == "wait":
            # Default wait of 1 second if no specific duration
            await asyncio.sleep(1)
            return True

        return False

    except Exception as e:
        typer.echo(f"  ERROR: {e}", err=True)
        return False


async def replay_recording(recording_path: Path, headless: bool = False) -> tuple[int, int]:
    """Replay a recording. Returns (success_count, total_count)."""
    # Load recording
    events: list[RecordedEvent] = []
    metadata: dict[str, str] = {}

    with recording_path.open() as f:
        for i, line in enumerate(f):
            data = json.loads(line)
            if i == 0:
                # First line is metadata
                metadata = data
            else:
                events.append(RecordedEvent.model_validate(data))

    start_url = metadata.get("start_url", "about:blank")
    typer.echo(f"Replaying session: {metadata.get('session_id', 'unknown')}")
    typer.echo(f"Starting at: {start_url}")
    typer.echo(f"Events to replay: {len(events)}\n")

    success_count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        await page.goto(start_url)

        for i, event in enumerate(events):
            typer.echo(f"[{i + 1}/{len(events)}] {event.event_type}: ", nl=False)
            if await _replay_event(page, event):
                typer.echo("OK")
                success_count += 1
            else:
                typer.echo("FAILED")
                # Take screenshot on failure
                screenshot_path = recording_path.parent / f"{recording_path.stem}_error_{i}.png"
                await page.screenshot(path=screenshot_path)
                typer.echo(f"  Screenshot saved: {screenshot_path}")

        await browser.close()

    return success_count, len(events)


@app.command()
def replay(
    recording: Path = typer.Argument(..., help="Path to recording JSONL file"),
    headless: bool = typer.Option(False, "--headless", "-h", help="Run in headless mode"),
) -> None:
    """Replay a recorded browser session."""
    if not recording.exists():
        typer.echo(f"Recording not found: {recording}", err=True)
        raise typer.Exit(1)

    success, total = asyncio.run(replay_recording(recording, headless))

    typer.echo(f"\nReplay complete: {success}/{total} events succeeded")
    if success < total:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
