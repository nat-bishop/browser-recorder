"""Combined CLI for browser-agents.

Usage:
    browser-agents record <url>     Start recording browser interactions
    browser-agents replay <file>    Replay a workflow
    browser-agents convert <file>   Convert workflow events to action
    browser-agents --help           Show help
"""

import asyncio
import signal
from pathlib import Path

import typer

from browser_agents.converter import save_workflow
from browser_agents.playback import (
    DEFAULT_DELAY,
    DEFAULT_MOUSE_STEPS,
    replay_workflow,
)
from browser_agents.recorder import BrowserRecorder

app = typer.Typer(
    name="browser-agents",
    help="Record, replay, and convert browser interactions.",
    no_args_is_help=True,
    pretty_exceptions_short=True,  # Short traceback without local variables
)


@app.command()
def record(
    url: str = typer.Argument(..., help="URL to start recording from"),
    name: str | None = typer.Option(
        None, "--name", "-n", help="Human-readable name for this workflow"
    ),
    description: str | None = typer.Option(
        None, "--description", "-d", help="Description of what this workflow does"
    ),
    output_dir: Path = typer.Option(
        Path("workflows"), "--output", "-o", help="Directory to save workflows"
    ),
) -> None:
    """Record browser interactions to a workflow JSON file.

    Creates a session folder with:
    - workflow.json: The recorded events
    - screenshots/: Screenshots taken during recording

    Examples:
        browser-agents record https://example.com
        browser-agents record https://example.com -n "login-flow" -d "Login to example.com"
    """
    recorder = BrowserRecorder(url, output_dir)

    def handle_sigint(sig: int, frame: object) -> None:
        typer.echo("\nStopping recording...")
        recorder.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    workflow = asyncio.run(recorder.record())

    # Set optional name and description
    if name:
        workflow.name = name
    if description:
        workflow.description = description

    # Save in session folder (workflows/{session_id}/workflow.json)
    session_dir = output_dir / workflow.id
    session_dir.mkdir(parents=True, exist_ok=True)
    output_file = session_dir / "workflow.json"
    save_workflow(workflow, output_file)
    typer.echo(f"\nRecorded {len(workflow.events)} events")
    typer.echo(f"Saved to: {output_file}")


@app.command()
def replay(
    workflow_path: Path = typer.Argument(..., help="Path to workflow JSON file"),
    action: bool = typer.Option(
        False,
        "--action",
        "-a",
        help="Replay action steps instead of raw events",
    ),
    action_name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Name of action to replay (if workflow has multiple actions)",
    ),
    param: list[str] | None = typer.Option(
        None,
        "--param",
        "-p",
        help="Parameter substitution (key=value, can repeat)",
    ),
    demo: bool = typer.Option(
        False,
        "--demo",
        "-d",
        help="Visual demo mode with cursor indicator and smooth movement",
    ),
    guided: bool = typer.Option(
        False,
        "--guided",
        "-g",
        help="Guided mode: pause on errors and ask for user guidance",
    ),
    delay: float = typer.Option(
        DEFAULT_DELAY,
        "--delay",
        help="Seconds between events (with random jitter)",
    ),
    speed: int = typer.Option(
        DEFAULT_MOUSE_STEPS,
        "--speed",
        help="Mouse movement smoothness (steps, higher = slower)",
    ),
) -> None:
    """Replay a workflow.

    By default, replays raw recorded events. Use --action to replay the
    parameterized action steps instead (requires running 'convert' first).

    Examples:
        browser-agents replay workflows/abc123.json
        browser-agents replay workflows/abc123.json --action
        browser-agents replay workflows/abc123.json --action --name login_flow
        browser-agents replay workflows/abc123.json --action --param username=foo
    """
    if not workflow_path.exists():
        typer.echo(f"Workflow not found: {workflow_path}", err=True)
        raise typer.Exit(1)

    # Parse param flags into dict
    params: dict[str, str] = {}
    if param:
        for p in param:
            if "=" in p:
                key, value = p.split("=", 1)
                params[key] = value
            else:
                typer.echo(f"Invalid param format: {p} (expected key=value)", err=True)
                raise typer.Exit(1)

    success, total = asyncio.run(
        replay_workflow(
            workflow_path,
            use_action=action,
            action_name=action_name,
            params=params if params else None,
            demo=demo,
            delay=delay,
            mouse_steps=speed,
            guided=guided,
        )
    )

    if total == 0:
        raise typer.Exit(1)

    typer.echo(f"\nReplay complete: {success}/{total} succeeded")
    if success < total:
        raise typer.Exit(1)


@app.command()
def convert(
    workflow_path: Path = typer.Argument(..., help="Path to workflow JSON file"),
    description: str = typer.Option(
        ...,
        "--description",
        "-d",
        help="Describe what this workflow does (e.g., 'Add items to cart and checkout')",
    ),
) -> None:
    """Convert workflow events to an action definition using LLM analysis.

    Reads a workflow JSON file and uses an LLM (via Ollama) to:
    - Extract variable parameters (usernames, passwords, etc.)
    - Collapse verbose events into logical steps
    - Generate a clean, parameterized action definition

    The action is saved back to the same workflow file (in-place update).

    Examples:
        browser-agents convert workflows/abc123.json -d "Login and add items to cart"
    """
    # Import here to avoid loading LangChain on every CLI invocation
    from browser_agents.converter import (
        convert_workflow_to_action,
        load_workflow,
    )

    if not workflow_path.exists():
        typer.echo(f"Workflow not found: {workflow_path}", err=True)
        raise typer.Exit(1)

    # Load workflow
    typer.echo(f"Loading workflow: {workflow_path}")
    try:
        workflow = load_workflow(workflow_path)
    except Exception as e:
        typer.echo(f"Failed to load workflow: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {len(workflow.events)} events from {workflow.source_url}")
    if workflow.actions:
        typer.echo(f"Existing actions: {len(workflow.actions)}")
    typer.echo(f"Intent: {description}")
    typer.echo("Converting to action definition...")

    # Convert using LLM
    result = asyncio.run(convert_workflow_to_action(workflow, description=description))

    if isinstance(result, str):
        # Error string returned
        typer.echo(f"Conversion failed: {result}", err=True)
        raise typer.Exit(1)

    # Success - append action to workflow and save
    workflow.actions.append(result)
    save_workflow(workflow, workflow_path)

    # Sanitize description for Windows console encoding
    safe_desc = result.description.encode("ascii", "replace").decode("ascii")
    typer.echo(f"\nCreated action: {result.name}")
    typer.echo(f"Description: {safe_desc}")
    typer.echo(f"Parameters: {len(result.parameters)}")
    typer.echo(f"Steps: {len(result.steps)}")
    typer.echo(f"Total actions in workflow: {len(workflow.actions)}")
    typer.echo(f"Updated: {workflow_path}")


@app.command(name="set-success")
def set_success(
    workflow_path: Path = typer.Argument(..., help="Path to workflow JSON file"),
    description: str = typer.Option(
        ..., "--description", "-d", help="Human description of success condition"
    ),
    url_pattern: str | None = typer.Option(
        None, "--url", "-u", help="Optional regex pattern for expected final URL"
    ),
    screenshot: Path | None = typer.Option(
        None, "--screenshot", "-s", help="Optional path to success screenshot"
    ),
) -> None:
    """Set the success condition for a workflow.

    The success condition defines what success looks like for replay verification.
    It can include:
    - A human-readable description (required)
    - A URL pattern to match (optional)
    - A screenshot of the expected final state (optional)

    Examples:
        browser-agents set-success workflows/abc/workflow.json -d "Order confirmation page"
        browser-agents set-success workflows/abc/workflow.json -d "Checkout complete" -u ".*checkout-complete.*"
    """
    from browser_agents.converter import load_workflow
    from browser_agents.models import SuccessCondition

    if not workflow_path.exists():
        typer.echo(f"Workflow not found: {workflow_path}", err=True)
        raise typer.Exit(1)

    # Load workflow
    try:
        workflow = load_workflow(workflow_path)
    except Exception as e:
        typer.echo(f"Failed to load workflow: {e}", err=True)
        raise typer.Exit(1)

    # Handle screenshot path - make it relative to workflow dir if in same tree
    screenshot_rel: str | None = None
    if screenshot:
        if not screenshot.exists():
            typer.echo(f"Screenshot not found: {screenshot}", err=True)
            raise typer.Exit(1)
        # Store as relative path if possible
        try:
            screenshot_rel = str(screenshot.relative_to(workflow_path.parent))
        except ValueError:
            screenshot_rel = str(screenshot)

    # Create and set success condition
    workflow.success_condition = SuccessCondition(
        description=description,
        url_pattern=url_pattern,
        screenshot_path=screenshot_rel,
    )

    # Save back
    save_workflow(workflow, workflow_path)
    typer.echo(f"Set success condition: {description}")
    if url_pattern:
        typer.echo(f"  URL pattern: {url_pattern}")
    if screenshot_rel:
        typer.echo(f"  Screenshot: {screenshot_rel}")
    typer.echo(f"Updated: {workflow_path}")


@app.command(name="list")
def list_workflows(
    workflows_dir: Path = typer.Argument(
        Path("workflows"), help="Directory containing workflow folders"
    ),
) -> None:
    """List all workflows with their names and actions.

    Scans the workflows directory for workflow.json files and displays
    a summary of each workflow including name, description, and actions.

    Examples:
        browser-agents list
        browser-agents list ./my-workflows
    """
    from browser_agents.converter import load_workflow

    if not workflows_dir.exists():
        typer.echo(f"Directory not found: {workflows_dir}", err=True)
        raise typer.Exit(1)

    # Find all workflow.json files
    workflow_files = list(workflows_dir.glob("**/workflow.json"))

    if not workflow_files:
        typer.echo(f"No workflows found in: {workflows_dir}")
        return

    typer.echo(f"Found {len(workflow_files)} workflow(s):\n")

    for wf_path in sorted(workflow_files):
        try:
            workflow = load_workflow(wf_path)

            # Display workflow info
            name = workflow.name or workflow.id
            desc = workflow.description or f"(from {workflow.source_url})"
            # Sanitize for Windows console
            desc = desc.encode("ascii", "replace").decode("ascii")

            typer.echo(f"  {name}")
            typer.echo(f"    Path: {wf_path}")
            typer.echo(f"    Description: {desc}")
            typer.echo(f"    Events: {len(workflow.events)}")

            if workflow.actions:
                typer.echo(f"    Actions ({len(workflow.actions)}):")
                for action in workflow.actions:
                    action_desc = action.description.encode("ascii", "replace").decode("ascii")
                    typer.echo(f"      - {action.name}: {action_desc}")
            else:
                typer.echo("    Actions: (none - run 'convert' to create)")

            typer.echo("")

        except Exception as e:
            typer.echo(f"  [ERROR] {wf_path}: {e}", err=True)


if __name__ == "__main__":
    app()
