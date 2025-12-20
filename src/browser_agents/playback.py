"""Replay recorded browser sessions."""

import asyncio
import json
from pathlib import Path

import typer
from playwright.async_api import Page, async_playwright

from browser_agents.models import RecordedEvent

# Default demo mode settings
DEFAULT_DELAY = 0.3  # seconds between events
DEFAULT_MOUSE_STEPS = 20  # interpolation steps for smooth movement


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
            if event.selector and event.value is not None:
                await page.fill(event.selector, event.value)
            elif event.value:
                # Fallback: type without selector (legacy recordings)
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


async def replay_recording(
    recording_path: Path,
    headless: bool = False,
    demo: bool = False,
    delay: float = DEFAULT_DELAY,
    mouse_steps: int = DEFAULT_MOUSE_STEPS,
) -> tuple[int, int]:
    """Replay a recording. Returns (success_count, total_count).

    Args:
        recording_path: Path to the JSONL recording file
        headless: Run browser in headless mode
        demo: Enable visual demo mode with cursor indicator and smooth movement
        delay: Seconds to wait between events (demo mode)
        mouse_steps: Number of interpolation steps for mouse movement (demo mode)
    """
    # Import demo functions here to avoid circular import issues
    from browser_agents.demo import (
        click_effect,
        move_cursor_smoothly,
        setup_demo_cursor,
    )

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
    typer.echo(f"Events to replay: {len(events)}")
    if demo:
        typer.echo(f"Demo mode: delay={delay}s, steps={mouse_steps}")
    typer.echo("")

    success_count = 0

    async with async_playwright() as p:
        # Use slowMo in demo mode for smoother experience
        slow_mo = 50 if demo else 0
        browser = await p.chromium.launch(headless=headless, slow_mo=slow_mo)
        page = await browser.new_page()

        # Setup visual cursor in demo mode
        if demo:
            await setup_demo_cursor(page)

        await page.goto(start_url)

        for i, event in enumerate(events):
            # Add delay between events in demo mode
            if demo and delay > 0 and i > 0:
                await asyncio.sleep(delay)

            typer.echo(f"[{i + 1}/{len(events)}] {event.event_type}: ", nl=False)

            # In demo mode, move cursor smoothly before clicks
            if demo and event.event_type == "click":
                try:
                    if event.selector:
                        box = await page.locator(event.selector).bounding_box()
                        if box:
                            x = box["x"] + box["width"] / 2
                            y = box["y"] + box["height"] / 2
                            await move_cursor_smoothly(page, x, y, mouse_steps)
                            await click_effect(page)
                    elif event.x is not None and event.y is not None:
                        await move_cursor_smoothly(
                            page, float(event.x), float(event.y), mouse_steps
                        )
                        await click_effect(page)
                except Exception:
                    pass  # Continue with normal click if demo fails

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
