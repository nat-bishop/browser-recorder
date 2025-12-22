"""Replay recorded browser sessions."""

import asyncio
import random
from pathlib import Path

import typer
from playwright.async_api import Page, async_playwright

from browser_agents.converter import load_workflow
from browser_agents.models import ActionStep, RecordedEvent, StepAction

# Default demo mode settings
DEFAULT_DELAY = 0.3  # seconds between events
DEFAULT_MOUSE_STEPS = 20  # interpolation steps for smooth movement


def substitute_params(step: ActionStep, params: dict[str, str]) -> ActionStep:
    """Replace {param} placeholders with actual values.

    Args:
        step: The action step with placeholder values.
        params: Dictionary of parameter name -> value.

    Returns:
        A copy of the step with placeholders substituted.
    """
    if not step.value or not params:
        return step

    new_value = step.value
    for key, val in params.items():
        new_value = new_value.replace(f"{{{key}}}", val)

    return step.model_copy(update={"value": new_value})


async def _replay_action_step(page: Page, step: ActionStep) -> bool:
    """Replay a single action step. Returns True on success."""
    try:
        if step.action == StepAction.navigate:
            if step.target:
                await page.goto(step.target)
            return True

        elif step.action == StepAction.click:
            if step.target:
                await page.click(step.target)
            elif step.fallback_coords and len(step.fallback_coords) >= 2:
                await page.mouse.click(step.fallback_coords[0], step.fallback_coords[1])
            return True

        elif step.action == StepAction.type:
            if step.target and step.value is not None:
                await page.fill(step.target, step.value)
            elif step.value:
                await page.keyboard.type(step.value)
            return True

        elif step.action == StepAction.scroll:
            # Scroll to element or coordinates
            if step.target:
                await page.locator(step.target).scroll_into_view_if_needed()
            return True

        elif step.action == StepAction.wait:
            await asyncio.sleep(1)
            return True

        return False

    except Exception as e:
        typer.echo(f"  ERROR: {e}", err=True)
        return False


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


async def replay_workflow(
    workflow_path: Path,
    use_action: bool = False,
    params: dict[str, str] | None = None,
    demo: bool = False,
    delay: float = DEFAULT_DELAY,
    mouse_steps: int = DEFAULT_MOUSE_STEPS,
) -> tuple[int, int]:
    """Replay a workflow. Returns (success_count, total_count).

    Args:
        workflow_path: Path to the .json workflow file
        use_action: If True, replay action steps; if False, replay raw events
        params: Parameter substitutions for action replay (e.g., {"username": "foo"})
        demo: Enable visual demo mode with cursor indicator and smooth movement
        delay: Seconds to wait between events (with +/- 50% jitter)
        mouse_steps: Number of interpolation steps for mouse movement (demo mode)
    """
    # Import demo functions here to avoid circular import issues
    from browser_agents.demo import (
        click_effect,
        move_cursor_smoothly,
        setup_demo_cursor,
    )

    # Load workflow
    workflow = load_workflow(workflow_path)

    # Determine what to replay
    if use_action:
        if not workflow.action:
            typer.echo("ERROR: Workflow has no action defined. Run 'convert' first.", err=True)
            return 0, 0
        steps = workflow.action.steps
        if params:
            steps = [substitute_params(step, params) for step in steps]
        typer.echo(f"Replaying action: {workflow.action.name}")
        typer.echo(f"Description: {workflow.action.description}")
        typer.echo(f"Steps: {len(steps)}")
    else:
        events = workflow.events
        typer.echo(f"Replaying workflow: {workflow.id}")
        typer.echo(f"Events: {len(events)}")

    typer.echo(f"Starting at: {workflow.source_url}")
    if demo:
        typer.echo(f"Demo mode: delay={delay}s, steps={mouse_steps}")
    typer.echo("")

    success_count = 0

    async with async_playwright() as p:
        # Use slowMo in demo mode for smoother experience
        slow_mo = 50 if demo else 0
        browser = await p.chromium.launch(headless=False, slow_mo=slow_mo)
        page = await browser.new_page()

        # Setup visual cursor in demo mode
        if demo:
            await setup_demo_cursor(page)

        await page.goto(workflow.source_url)

        if use_action:
            # Replay action steps
            for i, step in enumerate(steps):
                if delay > 0 and i > 0:
                    jitter = delay * random.uniform(0.5, 1.5)
                    await asyncio.sleep(jitter)

                typer.echo(
                    f"[{i + 1}/{len(steps)}] {step.action.value}: {step.description} ", nl=False
                )

                if await _replay_action_step(page, step):
                    typer.echo("OK")
                    success_count += 1
                else:
                    typer.echo("FAILED")
                    screenshot_path = workflow_path.parent / f"{workflow_path.stem}_error_{i}.png"
                    await page.screenshot(path=screenshot_path)
                    typer.echo(f"  Screenshot saved: {screenshot_path}")

            total = len(steps)
        else:
            # Replay raw events
            events = workflow.events
            for i, event in enumerate(events):
                if delay > 0 and i > 0:
                    jitter = delay * random.uniform(0.5, 1.5)
                    await asyncio.sleep(jitter)

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
                    screenshot_path = workflow_path.parent / f"{workflow_path.stem}_error_{i}.png"
                    await page.screenshot(path=screenshot_path)
                    typer.echo(f"  Screenshot saved: {screenshot_path}")

            total = len(events)

        await browser.close()

    return success_count, total
