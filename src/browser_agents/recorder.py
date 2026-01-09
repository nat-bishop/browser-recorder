"""Browser event recorder using Codegen-style selectors.

Uses injected JavaScript (selector-generator.js) to capture UI events
with multiple selector candidates per element.
"""

import asyncio
import signal
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from playwright.async_api import Page, async_playwright

from browser_agents.models import (
    RecordingSession,
    SelectorCandidate,
    SessionMetadata,
    UIEvent,
    UIEventType,
)

app = typer.Typer(help="Record browser interactions for automation.")

# Path to the shared selector generator JavaScript
SELECTOR_GENERATOR_PATH = Path(__file__).parent / "js" / "selector-generator.js"


def _load_recorder_script() -> str:
    """Load the recorder script with embedded selector generator."""
    # Load the selector generator JavaScript
    selector_generator = SELECTOR_GENERATOR_PATH.read_text(encoding="utf-8")

    # Wrap in IIFE that sets up event listeners
    return f"""
(() => {{
    // Prevent double-injection
    if (window.__recorderInitialized) return;
    window.__recorderInitialized = true;

    // Session start time for relative timestamps
    const sessionStartTime = performance.now();

    // ==========================================================================
    // Embedded selector generator
    // ==========================================================================
    {selector_generator}

    // ==========================================================================
    // Event handlers
    // ==========================================================================

    // Click listener (capture phase to get all clicks)
    document.addEventListener('click', (e) => {{
        if (!window.__recordEvent) return;

        const selectors = generateSelectors(e.target);

        window.__recordEvent({{
            id: crypto.randomUUID(),
            event_type: 'click',
            timestamp: new Date().toISOString(),
            relative_time_ms: Math.round(performance.now() - sessionStartTime),
            url: window.location.href,
            selectors: selectors,
            element_type: getElementType(e.target),
            element_label: findAssociatedLabel(e.target),
            element_text: e.target.innerText?.trim()?.substring(0, 200) || null,
            input_type: e.target.type || null,
            placeholder: e.target.placeholder || null,
            frame_type: window === window.top ? 'main' : 'iframe',
            frame_src: window !== window.top ? window.location.href : null,
            x: Math.round(e.clientX),
            y: Math.round(e.clientY)
        }});
    }}, true);

    // Double-click listener
    document.addEventListener('dblclick', (e) => {{
        if (!window.__recordEvent) return;

        const selectors = generateSelectors(e.target);

        window.__recordEvent({{
            id: crypto.randomUUID(),
            event_type: 'double_click',
            timestamp: new Date().toISOString(),
            relative_time_ms: Math.round(performance.now() - sessionStartTime),
            url: window.location.href,
            selectors: selectors,
            element_type: getElementType(e.target),
            element_label: findAssociatedLabel(e.target),
            frame_type: window === window.top ? 'main' : 'iframe',
            frame_src: window !== window.top ? window.location.href : null,
            x: Math.round(e.clientX),
            y: Math.round(e.clientY)
        }});
    }}, true);

    // Input listener for form fields
    document.addEventListener('input', (e) => {{
        if (!window.__recordEvent) return;
        if (!e.target || !e.target.tagName) return;

        const selectors = generateSelectors(e.target);

        window.__recordEvent({{
            id: crypto.randomUUID(),
            event_type: 'type',
            timestamp: new Date().toISOString(),
            relative_time_ms: Math.round(performance.now() - sessionStartTime),
            url: window.location.href,
            selectors: selectors,
            element_type: getElementType(e.target),
            element_label: findAssociatedLabel(e.target),
            input_type: e.target.type || null,
            placeholder: e.target.placeholder || null,
            value: e.target.value || '',
            frame_type: window === window.top ? 'main' : 'iframe',
            frame_src: window !== window.top ? window.location.href : null
        }});
    }}, true);

    // Change listener for select elements
    document.addEventListener('change', (e) => {{
        if (!window.__recordEvent) return;
        if (e.target.tagName?.toLowerCase() !== 'select') return;

        const selectors = generateSelectors(e.target);
        const selectedOption = e.target.options?.[e.target.selectedIndex];

        window.__recordEvent({{
            id: crypto.randomUUID(),
            event_type: 'select_option',
            timestamp: new Date().toISOString(),
            relative_time_ms: Math.round(performance.now() - sessionStartTime),
            url: window.location.href,
            selectors: selectors,
            element_type: 'select',
            element_label: findAssociatedLabel(e.target),
            value: selectedOption?.text || e.target.value,
            frame_type: window === window.top ? 'main' : 'iframe',
            frame_src: window !== window.top ? window.location.href : null
        }});
    }}, true);

    // Checkbox/radio change listener
    document.addEventListener('change', (e) => {{
        if (!window.__recordEvent) return;
        const type = e.target.type?.toLowerCase();
        if (type !== 'checkbox' && type !== 'radio') return;

        const selectors = generateSelectors(e.target);
        const isChecked = e.target.checked;

        window.__recordEvent({{
            id: crypto.randomUUID(),
            event_type: isChecked ? 'check' : 'uncheck',
            timestamp: new Date().toISOString(),
            relative_time_ms: Math.round(performance.now() - sessionStartTime),
            url: window.location.href,
            selectors: selectors,
            element_type: type,
            element_label: findAssociatedLabel(e.target),
            frame_type: window === window.top ? 'main' : 'iframe',
            frame_src: window !== window.top ? window.location.href : null
        }});
    }}, true);

    // Scroll listener (debounced)
    let scrollTimeout;
    window.addEventListener('scroll', () => {{
        clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => {{
            if (!window.__recordEvent) return;

            window.__recordEvent({{
                id: crypto.randomUUID(),
                event_type: 'scroll',
                timestamp: new Date().toISOString(),
                relative_time_ms: Math.round(performance.now() - sessionStartTime),
                url: window.location.href,
                selectors: [],
                scroll_x: Math.round(window.scrollX),
                scroll_y: Math.round(window.scrollY),
                frame_type: window === window.top ? 'main' : 'iframe',
                frame_src: window !== window.top ? window.location.href : null
            }});
        }}, 150);
    }}, true);

    // Keypress listener for special keys (Enter, Tab, Escape)
    document.addEventListener('keydown', (e) => {{
        if (!window.__recordEvent) return;

        const specialKeys = ['Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
        if (!specialKeys.includes(e.key)) return;

        // Don't record if user is typing in an input field (handled by input event)
        const tag = e.target.tagName?.toLowerCase();
        if ((tag === 'input' || tag === 'textarea') && e.key !== 'Enter' && e.key !== 'Tab' && e.key !== 'Escape') return;

        const selectors = generateSelectors(e.target);

        window.__recordEvent({{
            id: crypto.randomUUID(),
            event_type: 'key_press',
            timestamp: new Date().toISOString(),
            relative_time_ms: Math.round(performance.now() - sessionStartTime),
            url: window.location.href,
            selectors: selectors,
            key: e.key,
            frame_type: window === window.top ? 'main' : 'iframe',
            frame_src: window !== window.top ? window.location.href : null
        }});
    }}, true);
}})();
"""


class SessionRecorder:
    """Records browser events using Codegen-style selectors."""

    def __init__(self, start_url: str, output_dir: Path) -> None:
        self.start_url = start_url
        self.output_dir = output_dir
        self.session_id = f"sess_{uuid.uuid4().hex[:8]}"
        self.events: list[UIEvent] = []
        self.started_at = datetime.now(UTC)
        self._running = True
        self._page: Page | None = None
        self._start_time_ms: int = 0

    def _parse_selectors(
        self, selectors_data: list[dict] | None
    ) -> list[SelectorCandidate]:
        """Parse selector data from JavaScript into SelectorCandidate models."""
        if not selectors_data:
            return []

        result = []
        for sel in selectors_data:
            try:
                result.append(
                    SelectorCandidate(
                        strategy=sel.get("strategy", "css"),
                        value=sel.get("value", ""),
                        confidence=sel.get("confidence", "low"),
                        role=sel.get("role"),
                        name=sel.get("name"),
                    )
                )
            except Exception:
                # Skip malformed selectors
                continue
        return result

    def _add_event(self, event: UIEvent) -> None:
        """Add event and print for visibility."""
        self.events.append(event)

        # Build display string
        detail = ""
        if event.selectors:
            detail = event.selectors[0].value
        elif event.value:
            detail = event.value
        elif event.url:
            detail = event.url
        elif event.key:
            detail = f"key:{event.key}"

        if len(detail) > 50:
            detail = detail[:47] + "..."

        typer.echo(f"  [{event.event_type.value}] {detail}")

    async def _handle_page_event(self, event_data: dict[str, Any]) -> None:
        """Handle events received from injected page script."""
        try:
            event_type_str = event_data.get("event_type", "")

            # Map string to enum
            try:
                event_type = UIEventType(event_type_str)
            except ValueError:
                # Unknown event type, skip
                return

            # Parse selectors
            selectors = self._parse_selectors(event_data.get("selectors"))

            # Parse timestamp
            timestamp_str = event_data.get("timestamp")
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                timestamp = datetime.now(UTC)

            event = UIEvent(
                id=event_data.get("id", str(uuid.uuid4())),
                timestamp=timestamp,
                relative_time_ms=event_data.get("relative_time_ms", 0),
                event_type=event_type,
                url=event_data.get("url", ""),
                selectors=selectors,
                element_type=event_data.get("element_type"),
                element_label=event_data.get("element_label"),
                element_text=event_data.get("element_text"),
                input_type=event_data.get("input_type"),
                placeholder=event_data.get("placeholder"),
                value=event_data.get("value"),
                key=event_data.get("key"),
                scroll_x=event_data.get("scroll_x"),
                scroll_y=event_data.get("scroll_y"),
                frame_type=event_data.get("frame_type", "main"),
                frame_src=event_data.get("frame_src"),
                x=event_data.get("x"),
                y=event_data.get("y"),
            )

            self._add_event(event)

        except Exception as e:
            typer.echo(f"  [error parsing event: {e}]", err=True)

    async def _setup_event_capture(self, page: Page) -> None:
        """Set up event capture via injected JavaScript."""
        self._page = page

        # Expose callback to receive events from page JavaScript
        await page.expose_function("__recordEvent", self._handle_page_event)

        # Load and inject the recorder script
        recorder_script = _load_recorder_script()

        # Inject event listeners - runs automatically on every navigation
        await page.add_init_script(recorder_script)

        # Also run immediately for the current page
        try:
            await page.evaluate(recorder_script)
        except Exception:
            # CSP may block inline scripts on some sites - that's OK
            pass

        # Track page navigations
        async def on_navigate(frame: Any) -> None:
            if frame == page.main_frame:
                await asyncio.sleep(0.1)  # Let page settle

                event = UIEvent(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.now(UTC),
                    relative_time_ms=int(
                        (datetime.now(UTC) - self.started_at).total_seconds() * 1000
                    ),
                    event_type=UIEventType.NAVIGATE,
                    url=frame.url,
                    selectors=[],
                )
                self._add_event(event)

        page.on("framenavigated", lambda f: asyncio.create_task(on_navigate(f)))

    async def record(self) -> RecordingSession:
        """Start recording and wait for user to stop."""
        # Create session directory
        session_dir = self.output_dir / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create media directory for future video support
        media_dir = session_dir / "media"
        media_dir.mkdir(exist_ok=True)

        typer.echo(f"Starting recording session: {self.session_id}")
        typer.echo(f"Navigate to: {self.start_url}")
        typer.echo(f"Output: {session_dir}")
        typer.echo("Close the browser or press Ctrl+C to stop recording.\n")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            await self._setup_event_capture(page)
            await page.goto(self.start_url)

            # Set up page close detection
            page_closed = asyncio.Event()
            page.on("close", lambda: page_closed.set())

            # Wait for Ctrl+C or page close
            try:
                while self._running and not page_closed.is_set():
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass

            # Close browser gracefully
            try:
                await browser.close()
            except Exception:
                pass

        ended_at = datetime.now(UTC)
        duration_ms = int((ended_at - self.started_at).total_seconds() * 1000)

        return RecordingSession(
            metadata=SessionMetadata(
                id=self.session_id,
                started_at=self.started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                source_url=self.start_url,
            ),
            events=self.events,
        )

    def stop(self) -> None:
        """Signal the recorder to stop."""
        self._running = False


def save_session(session: RecordingSession, output_dir: Path) -> Path:
    """Save session to JSON file."""
    session_dir = output_dir / session.metadata.id
    session_dir.mkdir(parents=True, exist_ok=True)
    output_file = session_dir / "session.json"
    with output_file.open("w", encoding="utf-8") as f:
        f.write(session.model_dump_json(indent=2))
    return output_file


@app.command()
def record(
    url: str = typer.Argument(..., help="URL to start recording from"),
    output_dir: Path = typer.Option(
        Path("sessions"), "--output", "-o", help="Directory to save sessions"
    ),
) -> None:
    """Start recording browser interactions."""
    recorder = SessionRecorder(url, output_dir)

    # Handle Ctrl+C gracefully
    def handle_sigint(sig: int, frame: object) -> None:
        typer.echo("\nStopping recording...")
        recorder.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    # Run the recorder
    session = asyncio.run(recorder.record())

    # Save
    output_file = save_session(session, output_dir)
    typer.echo(f"\nRecorded {len(session.events)} events")
    typer.echo(f"Saved to: {output_file}")


if __name__ == "__main__":
    app()
