"""Browser integration tests.

These tests require Playwright browsers to be installed and are slow.
They test the full record → save → replay cycle.

Run with: uv run pytest tests/test_browser.py -v
Skip with: uv run pytest -m "not slow"

Setup:
    uv run playwright install chromium
"""

from pathlib import Path

import pytest

# Mark all tests in this file as slow and requiring a browser
pytestmark = [pytest.mark.slow, pytest.mark.browser]


class TestRecordingIntegration:
    """Full integration tests for recording functionality."""

    @pytest.mark.skip(reason="Requires browser - enable when testing locally")
    async def test_record_click_event(self, recordings_dir: Path) -> None:
        """Record a click event and verify it's captured.

        To run this test:
        1. Remove the @pytest.mark.skip decorator
        2. Run: uv run pytest tests/test_browser.py::TestRecordingIntegration::test_record_click_event -v
        """
        # Example implementation:
        # from browser_agents.recorder import BrowserRecorder
        #
        # recorder = BrowserRecorder("https://example.com", recordings_dir)
        # # Would need to programmatically trigger a click and stop recording
        # recording = await recorder.record()
        #
        # assert len(recording.events) > 0
        # assert any(e.event_type == "navigate" for e in recording.events)
        pass

    @pytest.mark.skip(reason="Requires browser - enable when testing locally")
    async def test_record_and_replay_roundtrip(self, recordings_dir: Path) -> None:
        """Full roundtrip: record actions, save, reload, replay.

        This is the core MVP test - proves the system works end-to-end.
        """
        # Example implementation:
        # 1. Record a session programmatically
        # 2. Save to JSONL
        # 3. Load the JSONL
        # 4. Replay and verify success
        pass


class TestPlaybackIntegration:
    """Full integration tests for playback functionality."""

    @pytest.mark.skip(reason="Requires browser - enable when testing locally")
    async def test_replay_navigate_event(self, sample_recording: Path) -> None:
        """Replay a recording with navigate events."""
        # from browser_agents.playback import replay_recording
        #
        # success, total = await replay_recording(sample_recording, headless=True)
        # assert success == total
        pass

    @pytest.mark.skip(reason="Requires browser - enable when testing locally")
    async def test_replay_with_invalid_selector_takes_screenshot(
        self, recordings_dir: Path
    ) -> None:
        """When replay fails, a screenshot should be saved."""
        # Create a recording with an invalid selector
        # Replay and verify screenshot is created
        pass


# Example of a parameterized browser test
@pytest.mark.skip(reason="Requires browser - enable when testing locally")
@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://httpbin.org/html",
    ],
)
async def test_record_basic_navigation(url: str, recordings_dir: Path) -> None:
    """Test recording works on different sites."""
    pass
