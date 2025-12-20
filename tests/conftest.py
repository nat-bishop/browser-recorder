"""Shared pytest fixtures for browser-agents tests.

Fixtures here are automatically available to all test files.
See: https://docs.pytest.org/en/stable/reference/fixtures.html
"""

from pathlib import Path

import pytest


@pytest.fixture
def recordings_dir(tmp_path: Path) -> Path:
    """Temporary directory for test recordings.

    Uses pytest's tmp_path fixture which creates a unique temp dir per test.
    Automatically cleaned up after test completes.
    """
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    return recordings


@pytest.fixture
def sample_recording(recordings_dir: Path) -> Path:
    """Create a minimal valid recording for testing.

    Returns path to a JSONL file with:
    - Valid metadata header
    - One navigate event
    - One click event
    """
    recording = recordings_dir / "test_session.jsonl"
    recording.write_text(
        '{"session_id": "test123", "start_url": "https://example.com", "started_at": "2025-01-01T00:00:00+00:00"}\n'
        '{"timestamp": 1.0, "event_type": "navigate", "url": "https://example.com"}\n'
        '{"timestamp": 2.0, "event_type": "click", "selector": "#main-button", "x": 100, "y": 200}\n'
    )
    return recording


@pytest.fixture
def empty_recording(recordings_dir: Path) -> Path:
    """Create a recording with only metadata (no events)."""
    recording = recordings_dir / "empty_session.jsonl"
    recording.write_text(
        '{"session_id": "empty", "start_url": "https://example.com", "started_at": "2025-01-01T00:00:00+00:00"}\n'
    )
    return recording


@pytest.fixture
def invalid_recording(recordings_dir: Path) -> Path:
    """Create an invalid recording file for error testing."""
    recording = recordings_dir / "invalid.jsonl"
    recording.write_text("not valid json\n")
    return recording
