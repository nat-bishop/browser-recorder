"""Replay recorded browser sessions."""

import asyncio
import platform
import random
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import typer
import yaml
from playwright.async_api import Page, async_playwright

from browser_agents.converter import load_workflow
from browser_agents.models import (
    ActionStep,
    ErrorDiagnosis,
    RecordedEvent,
    StepAction,
    StepFixSuggestion,
)


class ErrorType(str, Enum):
    """Classification of step execution errors."""

    CONVERSION = "conversion"  # LLM generated wrong step (wrong action type, hallucinated)
    EXECUTION = "execution"  # Step correct but failed to run (timeout, not found)
    VERIFICATION = "verification"  # Step ran but produced wrong result


class GuidedAction(str, Enum):
    """User choices when guided replay encounters an error."""

    CONTINUE = "continue"  # Continue to next step (ignore error)
    RETRY = "retry"  # Retry the current step
    SKIP = "skip"  # Skip this step (this run only)
    DELETE = "delete"  # Delete this step from workflow
    RERECORD = "rerecord"  # Re-record from current state
    MANUAL_FIX = "manual_fix"  # User fixed it manually in browser
    DESCRIBE = "describe"  # User describes the fix in natural language
    APPLY_FIX = "apply_fix"  # Apply the LLM's proposed fix
    ABORT = "abort"  # Stop the replay


@dataclass
class StepResult:
    """Result of executing a step in guided mode."""

    success: bool
    error: str | None = None
    error_type: ErrorType | None = None
    screenshot_path: Path | None = None


@dataclass
class WorkflowModifications:
    """Track modifications made during guided replay for later saving."""

    deleted_indices: set[int] = field(default_factory=set)  # Step indices to delete
    replacements: dict[int, list[ActionStep]] = field(
        default_factory=dict
    )  # Index -> replacement steps

    @property
    def has_changes(self) -> bool:
        """Check if any modifications were made."""
        return bool(self.deleted_indices) or bool(self.replacements)

    def apply_to_steps(self, original_steps: list[ActionStep]) -> list[ActionStep]:
        """Apply all modifications to create the new step list.

        Handles deletions and replacements in correct order.
        """
        result: list[ActionStep] = []
        for i, step in enumerate(original_steps):
            if i in self.deleted_indices:
                # Skip deleted steps
                continue
            elif i in self.replacements:
                # Replace with new steps from re-recording
                result.extend(self.replacements[i])
            else:
                # Keep original step
                result.append(step)
        return result


# Default demo mode settings
DEFAULT_DELAY = 0.3  # seconds between events
DEFAULT_MOUSE_STEPS = 20  # interpolation steps for smooth movement


def _open_screenshot(path: Path) -> None:
    """Open screenshot in the system's default image viewer."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(path)], check=False)
        elif system == "Windows":
            subprocess.run(["start", "", str(path)], shell=True, check=False)
        else:  # Linux
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass  # Silently fail if can't open


async def _extract_page_context(
    page: "Page",
    max_chars: int = 8000,
) -> str:
    """Extract relevant HTML context from the page for LLM diagnosis.

    Extracts interactive elements (inputs, buttons, links, selects) as simplified
    HTML that the LLM can analyze to find correct selectors.

    Args:
        page: The Playwright page to extract from.
        max_chars: Maximum characters to return (truncates if exceeded).

    Returns:
        Simplified HTML of interactive elements on the page.
    """
    js_extract = """
    () => {
        const interactive = document.querySelectorAll(
            'input, button, a, select, textarea, [role="button"], [onclick], [data-testid]'
        );
        const results = [];
        for (const el of interactive) {
            const attrs = [];
            // Collect key attributes
            if (el.id) attrs.push(`id="${el.id}"`);
            if (el.name) attrs.push(`name="${el.name}"`);
            if (el.className && typeof el.className === 'string') {
                const classes = el.className.trim().split(/\\s+/).slice(0, 3).join(' ');
                if (classes) attrs.push(`class="${classes}"`);
            }
            if (el.getAttribute('data-testid')) {
                attrs.push(`data-testid="${el.getAttribute('data-testid')}"`);
            }
            if (el.getAttribute('aria-label')) {
                attrs.push(`aria-label="${el.getAttribute('aria-label')}"`);
            }
            if (el.placeholder) attrs.push(`placeholder="${el.placeholder}"`);
            if (el.type) attrs.push(`type="${el.type}"`);
            if (el.href) attrs.push(`href="${el.href.slice(0, 50)}"`);

            // Get visible text (truncated)
            const text = el.textContent?.trim().slice(0, 50) || '';
            const tag = el.tagName.toLowerCase();

            // Format as HTML-like string
            if (tag === 'select') {
                // Include options for select elements
                const options = Array.from(el.options || []).slice(0, 5).map(o =>
                    `  <option value="${o.value}">${o.text.slice(0, 30)}</option>`
                ).join('\\n');
                results.push(`<${tag} ${attrs.join(' ')}>\\n${options}\\n</${tag}>`);
            } else if (text && !['input', 'textarea'].includes(tag)) {
                results.push(`<${tag} ${attrs.join(' ')}>${text}</${tag}>`);
            } else {
                results.push(`<${tag} ${attrs.join(' ')} />`);
            }
        }
        return results.join('\\n');
    }
    """

    try:
        html = await page.evaluate(js_extract)
        # Truncate if needed
        if len(html) > max_chars:
            html = html[:max_chars] + "\n<!-- ... truncated ... -->"
        return html
    except Exception as e:
        return f"<!-- Could not extract page HTML: {e} -->"


def _classify_error(error: str, step: ActionStep) -> ErrorType:
    """Classify an error into conversion, execution, or verification type.

    Args:
        error: The error message from Playwright
        step: The action step that failed

    Returns:
        ErrorType indicating the category of error
    """
    error_lower = error.lower()

    # Conversion errors - LLM generated wrong step
    if "element is not an <input>" in error_lower:
        return ErrorType.CONVERSION
    if "element is not a <select>" in error_lower:
        return ErrorType.CONVERSION
    if "not an <input>, <textarea>" in error_lower:
        return ErrorType.CONVERSION

    # Execution errors - step might be correct but failed
    if "timeout" in error_lower:
        return ErrorType.EXECUTION
    if "waiting for locator" in error_lower:
        return ErrorType.EXECUTION
    if "not visible" in error_lower:
        return ErrorType.EXECUTION
    if "not found" in error_lower:
        return ErrorType.EXECUTION
    if "detached" in error_lower:
        return ErrorType.EXECUTION

    # Default to execution error
    return ErrorType.EXECUTION


def _get_plain_language_error(error: str, step: ActionStep) -> tuple[str, str | None]:
    """Convert Playwright error to plain language diagnosis and suggestion.

    Args:
        error: Raw Playwright error message
        step: The action step that failed

    Returns:
        Tuple of (diagnosis, suggestion). Suggestion may be None.
    """
    error_lower = error.lower()

    # Type on non-input element (common conversion error)
    if "not an <input>, <textarea>" in error_lower or "element is not an <input>" in error_lower:
        if step.action == StepAction.type and step.target:
            if "select" in step.target.lower():
                return (
                    "Tried to type into a <select> dropdown",
                    "Dropdowns need a 'select' action, not 'type'. "
                    "Did you actually change this dropdown during recording?",
                )
        return (
            "Tried to type into a non-text element",
            "This element doesn't accept text input. The step may be wrong.",
        )

    # Timeout
    if "timeout" in error_lower:
        return (
            "Element took too long to appear",
            "The page may be slow, or the selector may be wrong.",
        )

    # Element not found
    if "waiting for locator" in error_lower and "timeout" in error_lower:
        return (
            f"Could not find element: {step.target}",
            "The selector may have changed since recording.",
        )

    # Element not visible
    if "not visible" in error_lower:
        return (
            "Element exists but is hidden",
            "It may be covered by another element or not yet shown.",
        )

    # Default
    return (error[:200] if len(error) > 200 else error, None)


async def _interpret_user_feedback(
    step: ActionStep,
    error: str,
    feedback: str,
    page_html: str = "",
) -> StepFixSuggestion | None:
    """Use LLM to interpret user feedback and suggest a fix.

    Args:
        step: The action step that failed.
        error: The error message from Playwright.
        feedback: User's natural language description of the problem/fix.
        page_html: HTML of interactive elements on the page (for finding correct selectors).

    Returns:
        StepFixSuggestion on success, None if LLM unavailable.
    """
    from browser_agents.llm import get_structured_llm

    try:
        # Load prompt
        prompts_dir = Path(__file__).parent / "prompts"
        prompt_path = prompts_dir / "fix_step.yaml"
        with prompt_path.open(encoding="utf-8") as f:
            prompts = yaml.safe_load(f)

        # Build user content
        user_content = prompts["user_template"].format(
            action=step.action.value,
            target=step.target or "(none)",
            value=step.value or "(none)",
            description=step.description,
            error=error,
            feedback=feedback,
            page_html=page_html or "(not available)",
        )

        messages: list[tuple[str, str]] = [
            ("system", prompts["system_prompt"]),
            ("user", user_content),
        ]

        # Get structured LLM
        llm = get_structured_llm(StepFixSuggestion, temperature=0.0)
        result = await llm.ainvoke(messages)

        if isinstance(result, StepFixSuggestion):
            return result
        return None

    except Exception as e:
        typer.echo(f"  [LLM interpretation failed: {e}]", err=True)
        return None


async def _diagnose_error_with_llm(
    step: ActionStep,
    error: str,
    page_html: str = "",
) -> ErrorDiagnosis | None:
    """Use LLM to diagnose why a step failed.

    This provides more accurate and flexible error diagnosis than
    pattern matching, at the cost of an LLM call (~0.5-2s).

    Args:
        step: The action step that failed.
        error: The error message from Playwright.
        page_html: HTML of interactive elements on the page (for finding correct selectors).

    Returns:
        ErrorDiagnosis on success, None if LLM unavailable.
    """
    from browser_agents.llm import get_structured_llm

    try:
        # Load prompt
        prompts_dir = Path(__file__).parent / "prompts"
        prompt_path = prompts_dir / "diagnose_error.yaml"
        with prompt_path.open(encoding="utf-8") as f:
            prompts = yaml.safe_load(f)

        # Build user content
        user_content = prompts["user_template"].format(
            action=step.action.value,
            target=step.target or "(none)",
            value=step.value or "(none)",
            description=step.description,
            error=error,
            page_html=page_html or "(not available)",
        )

        messages: list[tuple[str, str]] = [
            ("system", prompts["system_prompt"]),
            ("user", user_content),
        ]

        # Get structured LLM with retry for transient errors
        llm = get_structured_llm(ErrorDiagnosis, temperature=0.0)
        retryable = llm.with_retry(
            retry_if_exception_type=(ConnectionError, TimeoutError),
            stop_after_attempt=2,
        )

        # Invoke LLM
        result = await retryable.ainvoke(messages)

        if isinstance(result, ErrorDiagnosis):
            return result
        return None

    except FileNotFoundError:
        typer.echo("  [LLM diagnosis unavailable: prompt file not found]", err=True)
        return None
    except yaml.YAMLError as e:
        typer.echo(f"  [LLM diagnosis unavailable: invalid prompt YAML - {e}]", err=True)
        return None
    except (ConnectionError, TimeoutError) as e:
        typer.echo(f"  [LLM diagnosis unavailable: connection failed - {e}]", err=True)
        return None


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


# Timeout for finding elements (5 seconds is enough to know if selector is wrong)
ELEMENT_TIMEOUT = 5000


async def _replay_action_step(page: Page, step: ActionStep) -> tuple[bool, str | None]:
    """Replay a single action step.

    Returns:
        Tuple of (success, error_message). error_message is None on success.
    """
    try:
        if step.action == StepAction.navigate:
            if step.target:
                await page.goto(step.target)
            return True, None

        elif step.action == StepAction.click:
            if step.target:
                await page.click(step.target, timeout=ELEMENT_TIMEOUT)
            elif step.fallback_coords and len(step.fallback_coords) >= 2:
                await page.mouse.click(step.fallback_coords[0], step.fallback_coords[1])
            return True, None

        elif step.action == StepAction.type:
            if step.target and step.value is not None:
                await page.fill(step.target, step.value, timeout=ELEMENT_TIMEOUT)
            elif step.value:
                await page.keyboard.type(step.value)
            return True, None

        elif step.action == StepAction.select:
            # Handle <select> dropdown elements
            if step.target and step.value is not None:
                await page.select_option(step.target, value=step.value, timeout=ELEMENT_TIMEOUT)
            return True, None

        elif step.action == StepAction.scroll:
            # Scroll to element or coordinates
            if step.target:
                await page.locator(step.target).scroll_into_view_if_needed(timeout=ELEMENT_TIMEOUT)
            return True, None

        elif step.action == StepAction.wait:
            await asyncio.sleep(1)
            return True, None

        return False, "Unknown action type"

    except Exception as e:
        return False, str(e)


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


async def _prompt_user_guidance(
    page: "Page",
    step_num: int,
    step: ActionStep,
    error: str,
    screenshot_path: Path | None,
    expected_screenshot: str | None,
) -> tuple[GuidedAction, ErrorDiagnosis | None, str]:
    """Prompt user for guidance when a step fails.

    Uses LLM for error diagnosis when available, falling back to
    pattern matching if LLM is unavailable.

    Shows context-aware options based on error type:
    - Conversion errors: Delete, Re-record, Skip, Abort
    - Execution errors: Retry, Re-record, Manual fix, Skip, Abort
    - Verification errors: Continue, Retry, Manual fix, Abort

    Returns:
        Tuple of (action, diagnosis, page_html). Diagnosis and page_html are returned
        so the caller can use them for APPLY_FIX and DESCRIBE actions.
    """
    # Extract page HTML for LLM context
    page_html = await _extract_page_context(page)

    # Try LLM-based diagnosis first (more accurate, now with page context)
    llm_diagnosis = await _diagnose_error_with_llm(step, error, page_html)

    if llm_diagnosis:
        # Map LLM error_type string to ErrorType enum
        error_type_map = {
            "conversion": ErrorType.CONVERSION,
            "execution": ErrorType.EXECUTION,
            "verification": ErrorType.VERIFICATION,
        }
        error_type = error_type_map.get(llm_diagnosis.error_type, ErrorType.EXECUTION)
        diagnosis = llm_diagnosis.explanation
        suggestion = llm_diagnosis.suggestion
        likely_cause = llm_diagnosis.likely_cause
    else:
        # Fall back to pattern matching
        error_type = _classify_error(error, step)
        diagnosis, suggestion = _get_plain_language_error(error, step)
        likely_cause = None

    # Header
    typer.echo("\n" + "=" * 60)
    typer.echo(f"STEP {step_num} FAILED: {step.description}")
    typer.echo("=" * 60)

    # Step details
    typer.echo(f"\nAction: {step.action.value}")
    typer.echo(f"Target: {step.target}")
    if step.value:
        typer.echo(f"Value: {step.value}")

    # Plain language diagnosis (sanitize for Windows console encoding)
    def _safe_echo(prefix: str, text: str) -> None:
        """Echo text safely on Windows by replacing unencodable chars."""
        safe_text = text.encode("ascii", "replace").decode("ascii")
        typer.echo(f"{prefix}{safe_text}")

    _safe_echo("\nDIAGNOSIS: ", diagnosis)
    if likely_cause:
        _safe_echo("CAUSE: ", likely_cause)
    if suggestion:
        _safe_echo("SUGGESTION: ", suggestion)

    # Check if we have a proposed fix from the LLM
    has_proposed_fix = (
        llm_diagnosis
        and llm_diagnosis.proposed_fix
        and llm_diagnosis.proposed_fix.confidence in ("high", "medium")
    )

    if has_proposed_fix:
        fix = llm_diagnosis.proposed_fix
        typer.echo(f"\nPROPOSED FIX ({fix.confidence} confidence):")
        _safe_echo("  ", fix.reasoning)
        if fix.new_target:
            typer.echo(f"  New selector: {fix.new_target}")
        if fix.new_action:
            typer.echo(f"  New action: {fix.new_action}")
        if fix.new_value:
            typer.echo(f"  New value: {fix.new_value}")

    # Screenshot handling
    if screenshot_path:
        typer.echo(f"\nScreenshot saved: {screenshot_path}")
        if typer.confirm("Open screenshot?", default=True):
            _open_screenshot(screenshot_path)

    if expected_screenshot:
        typer.echo(f"Expected state: {expected_screenshot}")

    # Context-aware options based on error type
    typer.echo("\nWhat would you like to do?")

    # Common options for all error types
    describe_choice = {"f": GuidedAction.DESCRIBE, "fix": GuidedAction.DESCRIBE}
    apply_fix_choice = {}
    if has_proposed_fix:
        apply_fix_choice = {"x": GuidedAction.APPLY_FIX, "apply": GuidedAction.APPLY_FIX}

    if error_type == ErrorType.CONVERSION:
        # LLM generated wrong step - offer to delete or re-record
        if has_proposed_fix:
            typer.echo("  [x] Apply suggested fix")
        typer.echo("  [d] Delete this step (remove from workflow)")
        typer.echo("  [r] Re-record (record correct action from here)")
        typer.echo("  [f] Describe the fix (tell me what's wrong)")
        typer.echo("  [s] Skip (this run only)")
        typer.echo("  [a] Abort replay")
        valid_choices = {
            **apply_fix_choice,
            "d": GuidedAction.DELETE,
            "delete": GuidedAction.DELETE,
            "r": GuidedAction.RERECORD,
            "rerecord": GuidedAction.RERECORD,
            "s": GuidedAction.SKIP,
            "skip": GuidedAction.SKIP,
            "a": GuidedAction.ABORT,
            "abort": GuidedAction.ABORT,
            **describe_choice,
        }
        default = "x" if has_proposed_fix else "d"
    elif error_type == ErrorType.EXECUTION:
        # Step might be correct but failed - offer retry options
        if has_proposed_fix:
            typer.echo("  [x] Apply suggested fix")
        typer.echo("  [t] Retry this step")
        typer.echo("  [r] Re-record (record correct action from here)")
        typer.echo("  [m] I fixed it manually (continue)")
        typer.echo("  [f] Describe the fix (tell me what's wrong)")
        typer.echo("  [s] Skip (this run only)")
        typer.echo("  [a] Abort replay")
        valid_choices = {
            **apply_fix_choice,
            "t": GuidedAction.RETRY,
            "retry": GuidedAction.RETRY,
            "r": GuidedAction.RERECORD,
            "rerecord": GuidedAction.RERECORD,
            "m": GuidedAction.MANUAL_FIX,
            "manual": GuidedAction.MANUAL_FIX,
            "s": GuidedAction.SKIP,
            "skip": GuidedAction.SKIP,
            "a": GuidedAction.ABORT,
            "abort": GuidedAction.ABORT,
            **describe_choice,
        }
        default = "x" if has_proposed_fix else "t"
    else:  # VERIFICATION
        # Step ran but result seems wrong
        if has_proposed_fix:
            typer.echo("  [x] Apply suggested fix")
        typer.echo("  [c] Continue anyway (looks fine)")
        typer.echo("  [t] Retry this step")
        typer.echo("  [m] I fixed it manually (continue)")
        typer.echo("  [f] Describe the fix (tell me what's wrong)")
        typer.echo("  [a] Abort replay")
        valid_choices = {
            **apply_fix_choice,
            "c": GuidedAction.CONTINUE,
            "continue": GuidedAction.CONTINUE,
            "t": GuidedAction.RETRY,
            "retry": GuidedAction.RETRY,
            "m": GuidedAction.MANUAL_FIX,
            "manual": GuidedAction.MANUAL_FIX,
            "a": GuidedAction.ABORT,
            "abort": GuidedAction.ABORT,
            **describe_choice,
        }
        default = "x" if has_proposed_fix else "c"

    while True:
        choice = typer.prompt("Choice", default=default).lower().strip()
        if choice in valid_choices:
            return valid_choices[choice], llm_diagnosis, page_html
        typer.echo(f"Invalid choice. Valid options: {', '.join(set(valid_choices.keys()))}")


async def _check_for_page_errors(page: Page) -> str | None:
    """Check for visible error messages on the page.

    Returns:
        Error text if found, None otherwise.
    """
    error_selectors = [
        ".error-message",
        ".error",
        "[data-error]",
        ".alert-error",
        ".alert-danger",
        "[role='alert']",
        ".error-message-container",
    ]

    for selector in error_selectors:
        try:
            error_el = page.locator(selector).first
            if await error_el.is_visible(timeout=500):
                error_text = await error_el.text_content()
                if error_text and error_text.strip():
                    return error_text.strip()
        except Exception:
            pass  # Element not found or timeout

    return None


async def _rerecord_from_here(
    page: Page,
    workflow_dir: Path,
) -> list[ActionStep] | None:
    """Record events from current browser state and convert to action steps.

    This allows the user to demonstrate the correct action when a step fails.
    The browser remains in its current state, and the user performs actions
    which are recorded and converted to replacement steps.

    Args:
        page: The Playwright page in its current state.
        workflow_dir: Directory to save any screenshots.

    Returns:
        List of new ActionSteps to replace the failed step, or None if cancelled.
    """
    import time
    from datetime import UTC, datetime

    from browser_agents.converter import convert_workflow_to_action
    from browser_agents.models import RecordedEvent, Workflow
    from browser_agents.recorder import RECORDER_SCRIPT

    events: list[RecordedEvent] = []
    _rerecord_counter = getattr(_rerecord_from_here, "_counter", 0)
    _rerecord_from_here._counter = _rerecord_counter + 1  # type: ignore[attr-defined]
    func_name = f"__rerecordEvent_{_rerecord_counter}"

    async def handle_event(event_data: dict) -> None:
        """Callback to collect events from the page."""
        event_type = event_data.get("type")
        if event_type == "click":
            events.append(
                RecordedEvent(
                    timestamp=time.time(),
                    event_type="click",
                    selector=event_data.get("selector"),
                    x=event_data.get("x"),
                    y=event_data.get("y"),
                )
            )
            typer.echo(f"  [click] {event_data.get('selector', 'unknown')}")
        elif event_type == "input":
            events.append(
                RecordedEvent(
                    timestamp=time.time(),
                    event_type="type",
                    selector=event_data.get("selector"),
                    value=event_data.get("value"),
                )
            )
            val = event_data.get("value", "")
            display_val = val[:30] + "..." if len(val) > 30 else val
            typer.echo(f"  [type] {display_val}")
        elif event_type == "scroll":
            events.append(
                RecordedEvent(
                    timestamp=time.time(),
                    event_type="scroll",
                    scroll_x=event_data.get("scrollX"),
                    scroll_y=event_data.get("scrollY"),
                )
            )

    typer.echo("\n" + "=" * 60)
    typer.echo("RE-RECORDING MODE")
    typer.echo("=" * 60)
    typer.echo("Perform the correct action(s) in the browser.")
    typer.echo("Events will appear below as you interact.")
    typer.echo("")

    # Expose the event handler with a unique name (in case of multiple re-records)
    await page.expose_function(func_name, handle_event)

    # Inject modified recorder script that uses our unique function name
    modified_script = RECORDER_SCRIPT.replace("__recordEvent", func_name)
    await page.add_init_script(modified_script)
    try:
        await page.evaluate(modified_script)
    except Exception:
        pass  # CSP may block inline scripts

    typer.echo("Recording... Press Enter when done.\n")

    # Wait for user input (run in executor to not block async event loop)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: input())

    if not events:
        typer.echo("No events recorded. Cancelling re-record.")
        return None

    typer.echo(f"\nRecorded {len(events)} events. Converting to action steps...")

    # Create a temporary workflow for conversion
    temp_workflow = Workflow(
        id="rerecord",
        source_url=page.url,
        created_at=datetime.now(UTC),
        events=events,
    )

    # Convert to action steps via LLM
    result = await convert_workflow_to_action(
        temp_workflow, description="Re-recorded action to replace failed step"
    )
    if isinstance(result, str):
        typer.echo(f"Conversion failed: {result}")
        return None

    typer.echo(f"Created {len(result.steps)} action steps:")
    for i, step in enumerate(result.steps):
        typer.echo(f"  {i + 1}. [{step.action.value}] {step.description}")

    return result.steps


async def replay_workflow(
    workflow_path: Path,
    use_action: bool = False,
    action_name: str | None = None,
    params: dict[str, str] | None = None,
    demo: bool = False,
    delay: float = DEFAULT_DELAY,
    mouse_steps: int = DEFAULT_MOUSE_STEPS,
    guided: bool = False,
) -> tuple[int, int]:
    """Replay a workflow. Returns (success_count, total_count).

    Args:
        workflow_path: Path to the .json workflow file
        use_action: If True, replay action steps; if False, replay raw events
        action_name: Name of specific action to replay (if workflow has multiple)
        params: Parameter substitutions for action replay (e.g., {"username": "foo"})
        demo: Enable visual demo mode with cursor indicator and smooth movement
        delay: Seconds to wait between events (with +/- 50% jitter)
        mouse_steps: Number of interpolation steps for mouse movement (demo mode)
        guided: Enable guided mode - pause on errors and ask user for guidance
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
        if not workflow.actions:
            typer.echo("ERROR: Workflow has no actions defined. Run 'convert' first.", err=True)
            return 0, 0

        # Select which action to replay
        if action_name:
            # Find action by name
            selected_action = next((a for a in workflow.actions if a.name == action_name), None)
            if not selected_action:
                typer.echo(f"ERROR: Action '{action_name}' not found.", err=True)
                typer.echo("Available actions:")
                for a in workflow.actions:
                    typer.echo(f"  - {a.name}: {a.description}")
                return 0, 0
        elif len(workflow.actions) == 1:
            # Only one action, use it
            selected_action = workflow.actions[0]
        else:
            # Multiple actions, ask user to choose
            typer.echo("Multiple actions available:")
            for i, a in enumerate(workflow.actions):
                typer.echo(f"  [{i + 1}] {a.name}: {a.description}")
            choice = typer.prompt("Select action number", default="1")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(workflow.actions):
                    selected_action = workflow.actions[idx]
                else:
                    typer.echo("Invalid selection.", err=True)
                    return 0, 0
            except ValueError:
                typer.echo("Invalid selection.", err=True)
                return 0, 0

        steps = selected_action.steps
        if params:
            steps = [substitute_params(step, params) for step in steps]
        typer.echo(f"Replaying action: {selected_action.name}")
        typer.echo(f"Description: {selected_action.description}")
        typer.echo(f"Steps: {len(steps)}")
    else:
        events = workflow.events
        typer.echo(f"Replaying workflow: {workflow.id}")
        typer.echo(f"Events: {len(events)}")

    typer.echo(f"Starting at: {workflow.source_url}")
    if demo:
        typer.echo(f"Demo mode: delay={delay}s, steps={mouse_steps}")
    if guided:
        typer.echo("Guided mode: will pause on errors for your input")
    typer.echo("")

    success_count = 0
    aborted = False
    modifications = WorkflowModifications()  # Track any changes made during replay

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
            i = 0
            while i < len(steps) and not aborted:
                step = steps[i]

                if delay > 0 and i > 0:
                    jitter = delay * random.uniform(0.5, 1.5)
                    await asyncio.sleep(jitter)

                typer.echo(
                    f"[{i + 1}/{len(steps)}] {step.action.value}: {step.description} ", nl=False
                )

                success, error = await _replay_action_step(page, step)

                # Also check for visible page errors (like form validation)
                if success and guided:
                    page_error = await _check_for_page_errors(page)
                    if page_error:
                        success = False
                        error = f"Page shows error: {page_error}"

                if success:
                    typer.echo("OK")
                    success_count += 1
                    i += 1
                else:
                    typer.echo("FAILED")
                    if error:
                        typer.echo(f"  ERROR: {error}", err=True)

                    # Take screenshot of current state (if browser still open)
                    screenshot_path = workflow_path.parent / f"{workflow_path.stem}_error_{i}.png"
                    try:
                        await page.screenshot(path=screenshot_path)
                        typer.echo(f"  Screenshot saved: {screenshot_path}")
                    except Exception:
                        typer.echo("  (Could not save screenshot - browser closed)")
                        break  # Exit loop if browser is closed

                    if guided:
                        # Get expected screenshot path if available
                        expected = step.expected_screenshot
                        if expected and not Path(expected).is_absolute():
                            expected = str(workflow_path.parent / expected)

                        # Ask user what to do (uses LLM for diagnosis)
                        action, diagnosis, page_html = await _prompt_user_guidance(
                            page=page,
                            step_num=i + 1,
                            step=step,
                            error=error or "Unknown error",
                            screenshot_path=screenshot_path,
                            expected_screenshot=expected,
                        )

                        if action == GuidedAction.APPLY_FIX:
                            # Apply the LLM's proposed fix
                            if diagnosis and diagnosis.proposed_fix:
                                fix = diagnosis.proposed_fix
                                typer.echo(f"Applying fix: {fix.fix_type}")

                                if fix.fix_type == "delete_step":
                                    modifications.deleted_indices.add(i)
                                    typer.echo("Step marked for deletion.")
                                    i += 1
                                else:
                                    # Create modified step
                                    updates: dict[str, object] = {}
                                    if fix.new_target:
                                        updates["target"] = fix.new_target
                                    if fix.new_action:
                                        updates["action"] = StepAction(fix.new_action)
                                    if fix.new_value:
                                        updates["value"] = fix.new_value

                                    new_step = step.model_copy(update=updates)
                                    modifications.replacements[i] = [new_step]
                                    steps[i] = new_step
                                    typer.echo("Step modified. Retrying...")
                                    # Don't increment - retry with fixed step
                            else:
                                typer.echo("No fix available. Skipping...")
                                i += 1
                        elif action == GuidedAction.CONTINUE:
                            typer.echo("Continuing to next step...")
                            i += 1
                        elif action == GuidedAction.RETRY:
                            typer.echo("Retrying step...")
                            # Don't increment i - will retry same step
                        elif action == GuidedAction.SKIP:
                            typer.echo("Skipping step (this run only)...")
                            i += 1
                        elif action == GuidedAction.DELETE:
                            typer.echo("Marking step for deletion...")
                            modifications.deleted_indices.add(i)
                            i += 1
                        elif action == GuidedAction.RERECORD:
                            # Record new events from current state
                            new_steps = await _rerecord_from_here(page, workflow_path.parent)
                            if new_steps:
                                if typer.confirm(
                                    f"Replace step {i + 1} with {len(new_steps)} new step(s)?",
                                    default=True,
                                ):
                                    modifications.replacements[i] = new_steps
                                    typer.echo("Replacement recorded. Continuing...")
                                    i += 1
                                else:
                                    typer.echo("Replacement cancelled. Skipping step...")
                                    i += 1
                            else:
                                typer.echo("Re-record cancelled. Skipping step...")
                                i += 1
                        elif action == GuidedAction.MANUAL_FIX:
                            typer.echo("Continuing from your manual fix...")
                            i += 1
                        elif action == GuidedAction.DESCRIBE:
                            # Get user's description of the problem/fix
                            typer.echo("\nDescribe what's wrong or how to fix it:")
                            feedback = typer.prompt("Your feedback")

                            typer.echo("Interpreting your feedback...")
                            fix = await _interpret_user_feedback(
                                step, error or "Unknown error", feedback, page_html
                            )

                            if fix:
                                typer.echo(f"\nSuggested fix: {fix.fix_type.upper()}")
                                typer.echo(f"Reason: {fix.explanation}")

                                if fix.fix_type == "delete":
                                    if typer.confirm("Delete this step?", default=True):
                                        modifications.deleted_indices.add(i)
                                        typer.echo("Step marked for deletion.")
                                        i += 1
                                    else:
                                        typer.echo("Skipping step for now...")
                                        i += 1
                                elif fix.fix_type == "modify":
                                    typer.echo("\nProposed changes:")
                                    if fix.new_action:
                                        typer.echo(f"  Action: {fix.new_action}")
                                    if fix.new_target:
                                        typer.echo(f"  Target: {fix.new_target}")
                                    if fix.new_value:
                                        typer.echo(f"  Value: {fix.new_value}")
                                    if fix.new_description:
                                        typer.echo(f"  Description: {fix.new_description}")

                                    if typer.confirm("Apply this fix?", default=True):
                                        # Create modified step
                                        new_step = step.model_copy(
                                            update={
                                                k: v
                                                for k, v in {
                                                    "action": (
                                                        StepAction(fix.new_action)
                                                        if fix.new_action
                                                        else None
                                                    ),
                                                    "target": fix.new_target,
                                                    "value": fix.new_value,
                                                    "description": fix.new_description,
                                                }.items()
                                                if v is not None
                                            }
                                        )
                                        modifications.replacements[i] = [new_step]
                                        # Update steps list for immediate retry
                                        steps[i] = new_step
                                        typer.echo("Step modified. Retrying...")
                                        # Don't increment - retry with fixed step
                                    else:
                                        typer.echo("Skipping step for now...")
                                        i += 1
                                else:  # keep
                                    typer.echo("Retrying step...")
                                    # Don't increment - retry
                            else:
                                typer.echo("Could not interpret feedback. Skipping...")
                                i += 1
                        elif action == GuidedAction.ABORT:
                            typer.echo("Aborting replay...")
                            aborted = True
                    else:
                        # Non-guided mode: just continue
                        i += 1

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
                    try:
                        screenshot_path = (
                            workflow_path.parent / f"{workflow_path.stem}_error_{i}.png"
                        )
                        await page.screenshot(path=screenshot_path)
                        typer.echo(f"  Screenshot saved: {screenshot_path}")
                    except Exception as e:
                        typer.echo(f"  Could not save screenshot: {e}", err=True)

            total = len(events)

        # Check success condition if defined and in guided mode
        if guided and use_action and workflow.success_condition and not aborted:
            typer.echo("\n" + "=" * 60)
            typer.echo("CHECKING SUCCESS CONDITION")
            typer.echo("=" * 60)
            typer.echo(f"Expected: {workflow.success_condition.description}")

            # Take final screenshot
            final_screenshot = workflow_path.parent / f"{workflow_path.stem}_final.png"
            await page.screenshot(path=final_screenshot)
            typer.echo(f"Final screenshot: {final_screenshot}")

            # Check URL pattern if specified
            if workflow.success_condition.url_pattern:
                import re

                current_url = page.url
                if re.search(workflow.success_condition.url_pattern, current_url):
                    typer.echo(f"URL matches pattern: {current_url}")
                else:
                    typer.echo(f"URL does NOT match pattern: {current_url}")

            if workflow.success_condition.screenshot_path:
                expected_path = workflow.success_condition.screenshot_path
                if not Path(expected_path).is_absolute():
                    expected_path = str(workflow_path.parent / expected_path)
                typer.echo(f"Expected screenshot: {expected_path}")

            # Ask user to verify
            typer.echo("\nDoes the final state match the success condition?")
            confirmed = typer.confirm("Success?", default=True)
            if confirmed:
                typer.echo("Workflow completed successfully!")
            else:
                typer.echo("Workflow did not meet success condition.")

        # Prompt to save modifications if any were made
        if guided and use_action and modifications.has_changes:
            typer.echo("\n" + "=" * 60)
            typer.echo("WORKFLOW MODIFICATIONS")
            typer.echo("=" * 60)

            if modifications.deleted_indices:
                typer.echo(f"Steps deleted: {sorted(modifications.deleted_indices)}")
            if modifications.replacements:
                for idx, new_steps in modifications.replacements.items():
                    typer.echo(f"Step {idx + 1} replaced with {len(new_steps)} new step(s)")

            if typer.confirm("\nSave these changes to the workflow?", default=True):
                # Apply modifications and save
                from browser_agents.converter import save_workflow

                # Update the selected action's steps
                new_steps = modifications.apply_to_steps(selected_action.steps)
                selected_action.steps = new_steps
                save_workflow(workflow, workflow_path)
                typer.echo(f"Saved updated workflow to: {workflow_path}")
                typer.echo(f"Action '{selected_action.name}' now has {len(new_steps)} steps")
            else:
                typer.echo("Changes discarded.")

        await browser.close()

    return success_count, total
