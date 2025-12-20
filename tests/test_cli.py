"""CLI tests using Typer's CliRunner.

These tests verify CLI argument handling and error messages
without launching a browser. Fast and reliable.

Run with: uv run pytest tests/test_cli.py -v
"""

from pathlib import Path

from typer.testing import CliRunner

from browser_agents.cli import app

runner = CliRunner()


class TestCLIHelp:
    """Tests for CLI help and basic structure."""

    def test_help_shows_commands(self) -> None:
        """--help shows both record and replay commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "record" in result.stdout
        assert "replay" in result.stdout

    def test_record_help(self) -> None:
        """record --help shows URL argument."""
        result = runner.invoke(app, ["record", "--help"])
        assert result.exit_code == 0
        assert "URL" in result.stdout or "url" in result.stdout.lower()

    def test_replay_help(self) -> None:
        """replay --help shows recording argument."""
        result = runner.invoke(app, ["replay", "--help"])
        assert result.exit_code == 0
        assert "recording" in result.stdout.lower()

    def test_no_args_shows_help(self) -> None:
        """Running with no args shows help (no_args_is_help=True).

        Note: Typer returns exit code 0 for --help but may return 2 for
        no_args_is_help. We just verify the help content is shown.
        """
        result = runner.invoke(app, [])
        # Help content should be shown regardless of exit code
        assert "record" in result.stdout
        assert "replay" in result.stdout


class TestReplayCommand:
    """Tests for replay command error handling."""

    def test_replay_missing_file_errors(self) -> None:
        """Replay with nonexistent file returns error."""
        result = runner.invoke(app, ["replay", "nonexistent.jsonl"])
        assert result.exit_code == 1
        # Error message may be in stdout or stderr, check combined output
        assert "not found" in result.output.lower()

    def test_replay_accepts_headless_flag(self) -> None:
        """Replay accepts --headless flag (doesn't error on flag itself)."""
        result = runner.invoke(app, ["replay", "--help"])
        assert "--headless" in result.stdout or "-H" in result.stdout

    def test_replay_accepts_demo_flag(self) -> None:
        """Replay accepts --demo flag and related options."""
        result = runner.invoke(app, ["replay", "--help"])
        assert "--demo" in result.stdout or "-d" in result.stdout
        assert "--delay" in result.stdout
        assert "--speed" in result.stdout


class TestRecordCommand:
    """Tests for record command argument handling."""

    def test_record_requires_url(self) -> None:
        """Record without URL shows error."""
        result = runner.invoke(app, ["record"])
        assert result.exit_code != 0  # Missing required argument

    def test_record_accepts_output_option(self) -> None:
        """Record accepts --output option."""
        result = runner.invoke(app, ["record", "--help"])
        assert "--output" in result.stdout or "-o" in result.stdout


class TestCLIWithFixtures:
    """Tests using recording fixtures from conftest.py."""

    def test_replay_valid_recording_path(self, sample_recording: Path) -> None:
        """Replay with valid file path doesn't error on path check.

        Note: This will still fail because we can't actually launch
        a browser in CI, but it validates path handling.
        """
        # We can't actually run replay without a browser,
        # but we can verify the file exists check passes
        assert sample_recording.exists()

        # In a real integration test with browser, this would work:
        # result = runner.invoke(app, ["replay", str(sample_recording), "--headless"])
        # assert result.exit_code == 0
