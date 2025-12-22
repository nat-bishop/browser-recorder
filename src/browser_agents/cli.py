"""Combined CLI for browser-agents.

Usage:
    browser-agents record <url>     Start recording browser interactions
    browser-agents replay <file>    Replay a recorded session
    browser-agents convert <file>   Convert recording to action definition
    browser-agents --help           Show help
"""

import asyncio
import signal
from pathlib import Path

import typer

from browser_agents.playback import (
    DEFAULT_DELAY,
    DEFAULT_MOUSE_STEPS,
    replay_recording,
)
from browser_agents.recorder import BrowserRecorder, _save_recording

app = typer.Typer(
    name="browser-agents",
    help="Record, replay, and convert browser interactions.",
    no_args_is_help=True,
)


@app.command()
def record(
    url: str = typer.Argument(..., help="URL to start recording from"),
    output_dir: Path = typer.Option(
        Path("recordings"), "--output", "-o", help="Directory to save recordings"
    ),
) -> None:
    """Record browser interactions to a JSONL file."""
    recorder = BrowserRecorder(url, output_dir)

    def handle_sigint(sig: int, frame: object) -> None:
        typer.echo("\nStopping recording...")
        recorder.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    recording = asyncio.run(recorder.record())

    output_file = _save_recording(recording, output_dir)
    typer.echo(f"\nRecorded {len(recording.events)} events")
    typer.echo(f"Saved to: {output_file}")


@app.command()
def replay(
    recording: Path = typer.Argument(..., help="Path to recording JSONL file"),
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
    """Replay a recorded browser session.

    Use --demo for visual review with a visible cursor and smooth movement.
    """
    if not recording.exists():
        typer.echo(f"Recording not found: {recording}", err=True)
        raise typer.Exit(1)

    success, total = asyncio.run(
        replay_recording(
            recording,
            demo=demo,
            delay=delay,
            mouse_steps=speed,
        )
    )

    typer.echo(f"\nReplay complete: {success}/{total} events succeeded")
    if success < total:
        raise typer.Exit(1)


@app.command()
def convert(
    recording_path: Path = typer.Argument(..., help="Path to recording JSONL file"),
    output_dir: Path = typer.Option(
        Path("actions"), "--output", "-o", help="Directory to save action definitions"
    ),
    temperature: float = typer.Option(
        0.0, "--temperature", "-t", help="LLM temperature (0.0 = deterministic)"
    ),
) -> None:
    """Convert a recording to a reusable action definition using LLM analysis.

    Reads a raw recording JSONL file and uses an LLM (via Ollama) to:
    - Extract variable parameters (usernames, passwords, etc.)
    - Collapse verbose events into logical steps
    - Generate a clean, parameterized action definition

    The output is saved as a JSON file in the actions/ directory.

    Examples:
        browser-agents convert recordings/abc123.jsonl
        browser-agents convert recordings/abc123.jsonl --output ./my-actions
    """
    # Import here to avoid loading LangChain on every CLI invocation
    from browser_agents.converter import convert_recording_to_action, load_recording

    if not recording_path.exists():
        typer.echo(f"Recording not found: {recording_path}", err=True)
        raise typer.Exit(1)

    # Load recording
    typer.echo(f"Loading recording: {recording_path}")
    try:
        recording = load_recording(recording_path)
    except Exception as e:
        typer.echo(f"Failed to load recording: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {len(recording.events)} events from {recording.start_url}")
    typer.echo("Converting to action definition...")

    # Convert using LLM
    result = asyncio.run(convert_recording_to_action(recording, temperature=temperature))

    if isinstance(result, str):
        # Error string returned
        typer.echo(f"Conversion failed: {result}", err=True)
        raise typer.Exit(1)

    # Success - save action definition
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{result.name}.json"

    with output_file.open("w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))

    typer.echo(f"\nCreated action: {result.name}")
    typer.echo(f"Description: {result.description}")
    typer.echo(f"Parameters: {len(result.parameters)}")
    typer.echo(f"Steps: {len(result.steps)}")
    typer.echo(f"Saved to: {output_file}")


if __name__ == "__main__":
    app()
