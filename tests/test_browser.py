"""Browser integration tests.

These tests require Playwright browsers to be installed and are slow.
They test the full record → save → replay cycle.

Run with: uv run pytest tests/test_browser.py -v
Skip with: uv run pytest -m "not slow"

Setup:
    uv run playwright install chromium
"""

import asyncio
import json
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from browser_agents.models import RecordedEvent
from browser_agents.playback import _replay_event, replay_recording
from browser_agents.recorder import RECORDER_SCRIPT

# Mark all tests in this file as slow and requiring a browser
pytestmark = [pytest.mark.slow, pytest.mark.browser]


class TestPlaybackIntegration:
    """Full integration tests for playback functionality."""

    async def test_replay_navigate_event(self, sample_recording: Path) -> None:
        """Replay a recording with navigate events."""
        success, total = await replay_recording(sample_recording, headless=True)
        # sample_recording has 2 events: navigate + click
        # The click may fail (selector #main-button doesn't exist on example.com)
        # but navigate should succeed
        assert total == 2
        assert success >= 1  # At least navigation succeeded

    async def test_replay_navigate_only(self, recordings_dir: Path) -> None:
        """Replay a recording with only navigate events - should fully succeed."""
        # Create a simple recording with just navigation
        recording = recordings_dir / "nav_only.jsonl"
        recording.write_text(
            '{"session_id": "nav1", "start_url": "https://example.com", "started_at": "2025-01-01T00:00:00+00:00"}\n'
            '{"timestamp": 1.0, "event_type": "navigate", "url": "https://example.com"}\n'
        )

        success, total = await replay_recording(recording, headless=True)
        assert success == total == 1

    async def test_replay_with_invalid_selector_takes_screenshot(
        self, recordings_dir: Path
    ) -> None:
        """When replay fails on a click, a screenshot should be saved."""
        # Create a recording with an invalid selector
        recording = recordings_dir / "bad_selector.jsonl"
        recording.write_text(
            '{"session_id": "bad1", "start_url": "https://example.com", "started_at": "2025-01-01T00:00:00+00:00"}\n'
            '{"timestamp": 1.0, "event_type": "click", "selector": "#nonexistent-element-12345", "x": 100, "y": 100}\n'
        )

        success, total = await replay_recording(recording, headless=True)

        # Click should fail
        assert success == 0
        assert total == 1

        # Screenshot should be created
        screenshot = recordings_dir / "bad_selector_error_0.png"
        assert screenshot.exists(), "Screenshot should be saved on failure"
        assert screenshot.stat().st_size > 0, "Screenshot should not be empty"

    async def test_replay_type_event_fills_input(self, recordings_dir: Path) -> None:
        """Replay a type event correctly fills the input using selector."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Set up a page with an input field
            await page.set_content('<input id="test-input" />')

            # Replay the type event directly
            event = RecordedEvent(
                timestamp=1.0,
                event_type="type",
                selector="#test-input",
                value="hello world",
            )
            result = await _replay_event(page, event)

            # Verify
            assert result is True, "Type event should succeed"
            assert await page.input_value("#test-input") == "hello world"

            await browser.close()


class TestRecordingIntegration:
    """Full integration tests for recording functionality."""

    async def test_record_captures_navigation(self, recordings_dir: Path) -> None:
        """Record a page load and verify navigation event is captured."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Set up recording manually (simulating what BrowserRecorder does)
            events: list[RecordedEvent] = []

            async def handle_event(data: dict) -> None:
                if data.get("type") == "click":
                    events.append(
                        RecordedEvent(
                            timestamp=1.0,
                            event_type="click",
                            selector=data.get("selector"),
                            x=data.get("x"),
                            y=data.get("y"),
                        )
                    )

            await page.expose_function("__recordEvent", handle_event)
            await page.add_init_script(RECORDER_SCRIPT)

            # Track navigation
            nav_events: list[str] = []
            page.on(
                "framenavigated",
                lambda f: nav_events.append(f.url) if f == page.main_frame else None,
            )

            # Navigate
            await page.goto("https://example.com")
            await asyncio.sleep(0.5)  # Let events settle

            await browser.close()

        # Verify navigation was captured
        assert len(nav_events) >= 1
        assert "example.com" in nav_events[0]

    async def test_record_captures_click(self, recordings_dir: Path) -> None:
        """Record a click event via programmatic page.click() and verify it's captured."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Set up recording
            events: list[dict] = []

            async def handle_event(data: dict) -> None:
                events.append(data)

            await page.expose_function("__recordEvent", handle_event)
            await page.add_init_script(RECORDER_SCRIPT)

            # Navigate and click
            await page.goto("https://example.com")
            await page.evaluate(RECORDER_SCRIPT)  # Ensure script runs on this page
            await asyncio.sleep(0.3)

            # Click on the h1 element
            await page.click("h1")
            await asyncio.sleep(0.3)

            await browser.close()

        # Verify click was captured
        click_events = [e for e in events if e.get("type") == "click"]
        assert len(click_events) >= 1, f"Expected click events, got: {events}"
        assert click_events[0].get("selector") is not None

    async def test_record_captures_input(self, recordings_dir: Path) -> None:
        """Record typing in an input field."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Set up recording
            events: list[dict] = []

            async def handle_event(data: dict) -> None:
                events.append(data)

            await page.expose_function("__recordEvent", handle_event)
            await page.add_init_script(RECORDER_SCRIPT)

            # Create a page with an input field
            await page.set_content(
                '<html><body><input type="text" id="test-input" /></body></html>'
            )
            await page.evaluate(RECORDER_SCRIPT)
            await asyncio.sleep(0.2)

            # Type in the input
            await page.fill("#test-input", "hello world")
            await asyncio.sleep(0.3)

            await browser.close()

        # Verify input was captured
        input_events = [e for e in events if e.get("type") == "input"]
        assert len(input_events) >= 1, f"Expected input events, got: {events}"
        # The final value should contain our text
        assert any("hello" in str(e.get("value", "")) for e in input_events)


class TestRecordAndReplayRoundtrip:
    """Full roundtrip tests: record → save → replay."""

    async def test_roundtrip_click_on_example_com(self, recordings_dir: Path) -> None:
        """Record a click on example.com, save it, and replay it."""
        # Step 1: Record
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            events: list[RecordedEvent] = []

            async def handle_event(data: dict) -> None:
                if data.get("type") == "click":
                    events.append(
                        RecordedEvent(
                            timestamp=1.0,
                            event_type="click",
                            selector=data.get("selector"),
                            x=data.get("x"),
                            y=data.get("y"),
                        )
                    )

            await page.expose_function("__recordEvent", handle_event)
            await page.add_init_script(RECORDER_SCRIPT)

            await page.goto("https://example.com")
            await page.evaluate(RECORDER_SCRIPT)
            await asyncio.sleep(0.3)

            # Click the "More information..." link
            await page.click("a")
            await asyncio.sleep(0.3)

            await browser.close()

        assert len(events) >= 1, "Should have captured at least one click"

        # Step 2: Save to JSONL
        recording_file = recordings_dir / "roundtrip.jsonl"
        with recording_file.open("w") as f:
            f.write(
                json.dumps(
                    {
                        "session_id": "roundtrip1",
                        "start_url": "https://example.com",
                        "started_at": "2025-01-01T00:00:00+00:00",
                    }
                )
                + "\n"
            )
            for event in events:
                f.write(event.model_dump_json() + "\n")

        # Step 3: Replay
        success, total = await replay_recording(recording_file, headless=True)

        # The click should succeed (clicking on <a> element)
        assert total >= 1
        assert success >= 1, f"Replay failed: {success}/{total}"
