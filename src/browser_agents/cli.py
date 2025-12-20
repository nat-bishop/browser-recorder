"""Combined CLI for browser-agents.

Usage:
    browser-agents record <url>     Start recording browser interactions
    browser-agents replay <file>    Replay a recorded session
    browser-agents --help           Show help
"""

import asyncio
import signal
from pathlib import Path

import typer

from browser_agents.playback import replay_recording
from browser_agents.recorder import BrowserRecorder, _save_recording

app = typer.Typer(
    name="browser-agents",
    help="Record and replay browser interactions.",
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
    headless: bool = typer.Option(False, "--headless", "-H", help="Run in headless mode"),
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
