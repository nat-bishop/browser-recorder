"""CLI for browser-agents session recording and playback.

Usage:
    browser-agents import-trace <file>       Import from playwright-crx trace.zip
    browser-agents import-session <file>     Import session from Chrome extension
    browser-agents replay-session <path>     Replay a session
    browser-agents convert-session <path>    Convert session to action definition
    browser-agents list-sessions             List all sessions
    browser-agents --help                    Show help
"""

import asyncio
from pathlib import Path

import typer

app = typer.Typer(
    name="browser-agents",
    help="Record, replay, and convert browser interactions.",
    no_args_is_help=True,
    pretty_exceptions_short=True,  # Short traceback without local variables
)


def _normalize_session_path(session_path: Path) -> Path:
    """Convert directory or file path to session.json file path."""
    return session_path / "session.json" if session_path.is_dir() else session_path


def _create_session_directories(session_dir: Path) -> None:
    """Create session and media directories."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "media").mkdir(exist_ok=True)


@app.command(name="replay-session")
def replay_session(
    session_path: Path = typer.Argument(
        ..., help="Path to session.json or session directory"
    ),
    delay: int = typer.Option(
        100, "--delay", "-d", help="Delay between events in milliseconds"
    ),
    safe: bool = typer.Option(
        False,
        "--safe",
        "-s",
        help="Enable safe replay mode (block state-changing requests)",
    ),
    safe_mode: str = typer.Option(
        "block",
        "--mode",
        "-m",
        help="Safe mode type: block (abort requests), warn (log but allow), mock (fake success)",
    ),
    trace: bool = typer.Option(
        False,
        "--trace",
        "-t",
        help="Enable Playwright tracing (saves trace.zip for debugging)",
    ),
) -> None:
    """Replay a recording session using Codegen-style selectors.

    Uses the new session format with multi-selector resolution.
    Tries selectors in priority order (role > label > placeholder > text > testid > css)
    and falls back to coordinates when all selectors fail.

    Examples:
        browser-agents replay-session sessions/sess_abc123
        browser-agents replay-session sessions/sess_abc123/session.json
        browser-agents replay-session sessions/sess_abc123 --safe
        browser-agents replay-session sessions/sess_abc123 --safe --mode warn
        browser-agents replay-session sessions/sess_abc123 --trace
    """
    from browser_agents.models import UIEvent
    from browser_agents.playback import (
        PlaybackError,
        SafeReplayController,
        SafeReplayMode,
        SessionExecutor,
    )
    from browser_agents.storage import SessionStore

    # Normalize path and load session
    session_file = _normalize_session_path(session_path)
    if not session_file.exists():
        typer.echo(f"Session not found: {session_file}", err=True)
        raise typer.Exit(1)

    store = SessionStore(session_file.parent.parent)
    session_id = session_file.parent.name
    try:
        session = store.load_session(session_id)
    except Exception as e:
        typer.echo(f"Failed to load session: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Loaded session: {session.metadata.id}")
    typer.echo(f"Events: {len(session.events)}")
    typer.echo(f"Source: {session.metadata.source_url}")

    # Determine safe replay mode
    mode_map = {
        "block": SafeReplayMode.BLOCK,
        "warn": SafeReplayMode.WARN,
        "mock": SafeReplayMode.MOCK,
        "live": SafeReplayMode.LIVE,
    }
    replay_mode = (
        mode_map.get(safe_mode.lower(), SafeReplayMode.BLOCK)
        if safe
        else SafeReplayMode.LIVE
    )

    if safe:
        typer.echo(f"Safe mode: {replay_mode.value}")

    # Determine trace path
    trace_path = session_file.parent / "replay_trace.zip" if trace else None
    if trace_path:
        typer.echo(f"Tracing enabled: {trace_path}")

    # Progress callback
    def on_event(event: UIEvent, index: int, total: int) -> None:
        detail = ""
        if event.selector:
            detail = event.selector[:40]
        elif event.value:
            detail = event.value[:40]
        elif event.url:
            detail = event.url[:40]
        typer.echo(f"  [{index + 1}/{total}] {event.event_type.value}: {detail}")

    async def run_replay() -> tuple[int, int]:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            # Start tracing if enabled
            if trace_path:
                await context.tracing.start(screenshots=True, snapshots=True)

            success = 0
            failed = 0
            try:
                # Set up safe replay if enabled
                safe_controller = None
                if replay_mode != SafeReplayMode.LIVE:
                    safe_controller = SafeReplayController(page, replay_mode)
                    await safe_controller.setup()

                # Navigate to start URL
                await page.goto(session.metadata.source_url)

                # Create executor and replay events
                executor = SessionExecutor(page, delay_ms=delay)
                for i, event in enumerate(session.events):
                    try:
                        on_event(event, i, len(session.events))
                        await executor.replay_event(event)
                        success += 1
                    except PlaybackError as e:
                        typer.echo(f"    [FAILED] {e}", err=True)
                        failed += 1
                    except Exception as e:
                        typer.echo(f"    [ERROR] {e}", err=True)
                        failed += 1

                # Print safe replay report
                if safe_controller:
                    report = safe_controller.get_report()
                    if report["blocked_count"] > 0:
                        typer.echo(
                            f"\nSafe replay blocked {report['blocked_count']} requests"
                        )
            finally:
                # Stop tracing and save (even on error)
                if trace_path:
                    await context.tracing.stop(path=str(trace_path))
                    typer.echo(f"\nTrace saved to: {trace_path}")
                    typer.echo(f"View with: npx playwright show-trace {trace_path}")

                await browser.close()

            return success, failed

    success, failed = asyncio.run(run_replay())
    total = success + failed
    typer.echo(f"\nReplay complete: {success}/{total} events succeeded")
    if failed > 0:
        raise typer.Exit(1)


@app.command(name="import-session")
def import_session(
    source_file: Path = typer.Argument(
        ..., help="Path to session.json from Chrome extension export"
    ),
    output_dir: Path = typer.Option(
        Path("sessions"), "--output", "-o", help="Output directory"
    ),
) -> None:
    """Import a recording session from Chrome extension export.

    Validates the session JSON and copies it to the sessions directory.

    Examples:
        browser-agents import-session ~/Downloads/workflow-abc123.json
        browser-agents import-session export.json -o ./my-sessions
    """
    from browser_agents.models import RecordingSession

    if not source_file.exists():
        typer.echo(f"Source file not found: {source_file}", err=True)
        raise typer.Exit(1)

    # Load and validate
    try:
        content = source_file.read_text(encoding="utf-8")
        session = RecordingSession.model_validate_json(content)
    except Exception as e:
        typer.echo(f"Invalid session file: {e}", err=True)
        raise typer.Exit(1)

    # Create session and media directories
    session_dir = output_dir / session.metadata.id
    _create_session_directories(session_dir)

    # Copy video if present and exists
    if session.metadata.video:
        video_src = source_file.parent / session.metadata.video.path
        if video_src.exists():
            import shutil

            video_dst = session_dir / "media" / "recording.webm"
            shutil.copy(video_src, video_dst)
            session.metadata.video.path = "media/recording.webm"

    # Save session
    output_file = session_dir / "session.json"
    output_file.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    typer.echo(f"Imported session to: {session_dir}")
    typer.echo(f"  ID: {session.metadata.id}")
    typer.echo(f"  Events: {len(session.events)}")
    typer.echo(f"  Source: {session.metadata.source_url}")
    if session.metadata.video:
        typer.echo(f"  Video: {session.metadata.video.path}")


def _import_and_save_trace(
    trace_path: Path, output_dir: Path, verbose: bool = True
) -> Path:
    """Import a trace.zip and save as a session. Returns session directory."""
    import shutil

    from browser_agents.importers.trace_importer import import_trace

    session = import_trace(trace_path)

    if not session.events and verbose:
        typer.echo("Warning: No events found in trace", err=True)

    # Create session and media directories
    session_dir = output_dir / session.metadata.id
    _create_session_directories(session_dir)

    # Copy original trace.zip and save session
    shutil.copy(trace_path, session_dir / "trace.zip")
    (session_dir / "session.json").write_text(
        session.model_dump_json(indent=2), encoding="utf-8"
    )

    if verbose:
        typer.echo(f"Imported session to: {session_dir}")
        typer.echo(f"  ID: {session.metadata.id}")
        typer.echo(f"  Events: {len(session.events)}")
        typer.echo(f"  Network requests: {len(session.network_requests)}")
        typer.echo(f"  Source: {session.metadata.source_url}")
        typer.echo(f"  Trace: {session_dir / 'trace.zip'}")

    return session_dir


@app.command(name="import-trace")
def import_trace_cmd(
    trace_path: Path = typer.Argument(
        ..., help="Path to trace.zip from playwright-crx"
    ),
    output_dir: Path = typer.Option(
        Path("sessions"), "--output", "-o", help="Output directory"
    ),
) -> None:
    """Import a recording from playwright-crx trace.zip file.

    Parses the trace.zip file generated by playwright-crx recorder and
    converts it to the browser-agents session format.

    Examples:
        browser-agents import-trace ~/Downloads/trace.zip
        browser-agents import-trace recording.zip -o ./my-sessions
    """
    if not trace_path.exists():
        typer.echo(f"Trace file not found: {trace_path}", err=True)
        raise typer.Exit(1)

    if trace_path.suffix != ".zip":
        typer.echo(f"Expected .zip file, got: {trace_path.suffix}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Importing trace: {trace_path}")
    try:
        _import_and_save_trace(trace_path, output_dir)
    except Exception as e:
        typer.echo(f"Failed to import trace: {e}", err=True)
        raise typer.Exit(1)


@app.command(name="record")
def record(
    port: int = typer.Option(9222, "--port", "-p", help="Chrome debugging port"),
    output: Path = typer.Option(
        Path("recording_trace.zip"), "--output", "-o", help="Output trace file path"
    ),
    auto_import: bool = typer.Option(
        True, "--import/--no-import", help="Automatically import trace to sessions"
    ),
    output_dir: Path = typer.Option(
        Path("sessions"), "--sessions", "-s", help="Sessions directory for import"
    ),
) -> None:
    """Record browser actions via Chrome DevTools Protocol.

    Connects to a running Chrome instance, starts tracing, waits for you to
    perform actions, then saves the trace when you press Enter.

    Prerequisites:
        Launch Chrome with: chrome --remote-debugging-port=9222
        Or use: browser-agents launch-chrome

    Examples:
        browser-agents record
        browser-agents record --port 9223
        browser-agents record -o my_trace.zip --no-import
    """

    async def record_impl() -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            typer.echo(f"Connecting to Chrome on port {port}...")
            try:
                browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            except Exception as e:
                typer.echo(f"Failed to connect to Chrome: {e}", err=True)
                typer.echo(
                    "\nMake sure Chrome is running with --remote-debugging-port=9222"
                )
                typer.echo("Or run: browser-agents launch-chrome")
                raise typer.Exit(1)

            contexts = browser.contexts
            if not contexts:
                typer.echo("No browser contexts found. Open a tab in Chrome first.")
                raise typer.Exit(1)

            context = contexts[0]
            try:
                typer.echo("Starting trace recording...")
                await context.tracing.start(
                    screenshots=True, snapshots=True, sources=True
                )

                typer.echo("\n" + "=" * 50)
                typer.echo("RECORDING - Perform your actions in the browser")
                typer.echo("=" * 50)
                typer.echo("\nPress ENTER when done to stop recording...")

                # Wait for user input (blocking)
                await asyncio.get_event_loop().run_in_executor(None, input)

                typer.echo(f"\nStopping trace and saving to: {output}")
                await context.tracing.stop(path=str(output))
            finally:
                await browser.disconnect()

    asyncio.run(record_impl())

    typer.echo(f"Recording saved: {output}")

    if auto_import:
        typer.echo("\nImporting trace...")
        try:
            _import_and_save_trace(output, output_dir)
        except Exception as e:
            typer.echo(f"Failed to import trace: {e}", err=True)
            typer.echo("Trace file saved but not imported.")


@app.command(name="launch-chrome")
def launch_chrome(
    port: int = typer.Option(9222, "--port", "-p", help="Debugging port"),
    url: str = typer.Option("about:blank", "--url", "-u", help="Initial URL to open"),
) -> None:
    """Launch Chrome with remote debugging enabled.

    Finds Chrome on the system and launches it with --remote-debugging-port
    so that the record command can connect to it.

    Examples:
        browser-agents launch-chrome
        browser-agents launch-chrome --url https://example.com
        browser-agents launch-chrome --port 9223
    """
    import subprocess
    import sys

    # Find Chrome executable
    chrome_paths = []
    if sys.platform == "win32":
        chrome_paths = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path.home()
            / "AppData"
            / "Local"
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
        ]
    elif sys.platform == "darwin":
        chrome_paths = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    else:  # Linux
        chrome_paths = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
        ]

    chrome_exe = None
    for path in chrome_paths:
        if path.exists():
            chrome_exe = path
            break

    if chrome_exe is None:
        typer.echo("Chrome not found. Please install Chrome or specify path.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Launching Chrome with debugging port {port}...")
    typer.echo(f"  Executable: {chrome_exe}")

    cmd = [
        str(chrome_exe),
        f"--remote-debugging-port={port}",
        "--user-data-dir=" + str(Path.home() / ".browser-agents" / "chrome-profile"),
        url,
    ]

    # Launch Chrome in background
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS,
            )
        else:
            subprocess.Popen(cmd, start_new_session=True)
    except OSError as e:
        typer.echo(f"Failed to launch Chrome: {e}", err=True)
        raise typer.Exit(1)

    typer.echo("\nChrome launched! Now run:")
    typer.echo("  browser-agents record")


@app.command(name="convert-session")
def convert_session(
    session_path: Path = typer.Argument(
        ..., help="Path to session.json or session directory"
    ),
    description: str = typer.Option(
        ...,
        "--description",
        "-d",
        help="Describe what this workflow does (e.g., 'Login and add items to cart')",
    ),
) -> None:
    """Convert a recording session to an action definition using LLM analysis.

    Reads a session JSON file (from Chrome extension) and uses an LLM to:
    - Extract variable parameters (usernames, passwords, etc.)
    - Collapse verbose events into logical steps
    - Generate a clean, parameterized action definition

    The action is saved to sessions/{id}/processed/workflow.json

    Examples:
        browser-agents convert-session sessions/sess_abc123 -d "Login and add items to cart"
        browser-agents convert-session ~/Downloads/session.json -d "Search for products"
    """
    from browser_agents.converter import (
        convert_session_to_action,
        load_session,
        save_action_definition,
    )

    # Normalize path and determine session directory
    session_file = _normalize_session_path(session_path)
    session_dir = session_path if session_path.is_dir() else session_path.parent

    if not session_file.exists():
        typer.echo(f"Session not found: {session_file}", err=True)
        raise typer.Exit(1)

    # Load session
    typer.echo(f"Loading session: {session_file}")
    try:
        session = load_session(session_file)
    except Exception as e:
        typer.echo(f"Failed to load session: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {len(session.events)} events from {session.metadata.source_url}")
    typer.echo(f"Intent: {description}")
    typer.echo("Converting to action definition...")

    # Convert using LLM
    result = asyncio.run(convert_session_to_action(session, description=description))

    if isinstance(result, str):
        # Error string returned
        typer.echo(f"Conversion failed: {result}", err=True)
        raise typer.Exit(1)

    # Success - save action definition
    output_path = save_action_definition(result, session_dir)

    # Sanitize description for Windows console encoding
    safe_desc = result.description.encode("ascii", "replace").decode("ascii")
    typer.echo(f"\nCreated action: {result.name}")
    typer.echo(f"Description: {safe_desc}")
    typer.echo(f"Parameters: {len(result.parameters)}")
    typer.echo(f"Steps: {len(result.steps)}")
    typer.echo(f"Saved to: {output_path}")


@app.command(name="list-sessions")
def list_sessions(
    sessions_dir: Path = typer.Argument(
        Path("sessions"), help="Directory containing session folders"
    ),
) -> None:
    """List all recording sessions.

    Scans the sessions directory for session.json files and displays
    a summary of each session.

    Examples:
        browser-agents list-sessions
        browser-agents list-sessions ./my-sessions
    """
    from browser_agents.storage import SessionStore

    if not sessions_dir.exists():
        typer.echo(f"Directory not found: {sessions_dir}", err=True)
        raise typer.Exit(1)

    store = SessionStore(sessions_dir)
    session_ids = store.list_sessions()

    if not session_ids:
        typer.echo(f"No sessions found in: {sessions_dir}")
        return

    typer.echo(f"Found {len(session_ids)} session(s):\n")

    for session_id in session_ids:
        try:
            session = store.load_session(session_id)
            name = session.metadata.name or session.metadata.id
            url = session.metadata.source_url

            typer.echo(f"  {name}")
            typer.echo(f"    Path: {sessions_dir / session_id}")
            typer.echo(f"    Events: {len(session.events)}")
            typer.echo(f"    URL: {url}")
            if session.metadata.duration_ms:
                duration_s = session.metadata.duration_ms / 1000
                typer.echo(f"    Duration: {duration_s:.1f}s")
            typer.echo("")
        except Exception as e:
            typer.echo(f"  [ERROR] {session_id}: {e}", err=True)


if __name__ == "__main__":
    app()
