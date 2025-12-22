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
)


@app.command()
def record(
    url: str = typer.Argument(..., help="URL to start recording from"),
    output_dir: Path = typer.Option(
        Path("workflows"), "--output", "-o", help="Directory to save workflows"
    ),
) -> None:
    """Record browser interactions to a workflow JSON file."""
    recorder = BrowserRecorder(url, output_dir)

    def handle_sigint(sig: int, frame: object) -> None:
        typer.echo("\nStopping recording...")
        recorder.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    workflow = asyncio.run(recorder.record())

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{workflow.id}.json"
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
        browser-agents replay workflows/abc123.json --action --param username=foo --param password=bar
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
            params=params if params else None,
            demo=demo,
            delay=delay,
            mouse_steps=speed,
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
    temperature: float = typer.Option(
        0.0, "--temperature", "-t", help="LLM temperature (0.0 = deterministic)"
    ),
) -> None:
    """Convert workflow events to an action definition using LLM analysis.

    Reads a workflow JSON file and uses an LLM (via Ollama) to:
    - Extract variable parameters (usernames, passwords, etc.)
    - Collapse verbose events into logical steps
    - Generate a clean, parameterized action definition

    The action is saved back to the same workflow file (in-place update).

    Examples:
        browser-agents convert workflows/abc123.json
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
    typer.echo("Converting to action definition...")

    # Convert using LLM
    result = asyncio.run(convert_workflow_to_action(workflow, temperature=temperature))

    if isinstance(result, str):
        # Error string returned
        typer.echo(f"Conversion failed: {result}", err=True)
        raise typer.Exit(1)

    # Success - update workflow with action and save in-place
    workflow.action = result
    save_workflow(workflow, workflow_path)

    # Sanitize description for Windows console encoding
    safe_desc = result.description.encode("ascii", "replace").decode("ascii")
    typer.echo(f"\nCreated action: {result.name}")
    typer.echo(f"Description: {safe_desc}")
    typer.echo(f"Parameters: {len(result.parameters)}")
    typer.echo(f"Steps: {len(result.steps)}")
    typer.echo(f"Updated: {workflow_path}")


if __name__ == "__main__":
    app()
