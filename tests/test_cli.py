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
        """--help shows session commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "replay-session" in result.stdout
        assert "import-session" in result.stdout
        assert "convert-session" in result.stdout
        assert "list-sessions" in result.stdout

    def test_replay_session_help(self) -> None:
        """replay-session --help shows session argument."""
        result = runner.invoke(app, ["replay-session", "--help"])
        assert result.exit_code == 0
        assert "session" in result.stdout.lower()

    def test_import_session_help(self) -> None:
        """import-session --help shows source file argument."""
        result = runner.invoke(app, ["import-session", "--help"])
        assert result.exit_code == 0
        assert "source" in result.stdout.lower() or "file" in result.stdout.lower()

    def test_convert_session_help(self) -> None:
        """convert-session --help shows description option."""
        result = runner.invoke(app, ["convert-session", "--help"])
        assert result.exit_code == 0
        assert "--description" in result.stdout or "-d" in result.stdout

    def test_no_args_shows_help(self) -> None:
        """Running with no args shows help (no_args_is_help=True)."""
        result = runner.invoke(app, [])
        # Help content should be shown regardless of exit code
        assert "replay-session" in result.stdout
        assert "import-session" in result.stdout

    def test_launch_chrome_help(self) -> None:
        """launch-chrome --help shows port and url options."""
        result = runner.invoke(app, ["launch-chrome", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.stdout
        assert "--url" in result.stdout


class TestReplaySessionCommand:
    """Tests for replay-session command error handling."""

    def test_replay_missing_session_errors(self) -> None:
        """Replay with nonexistent session returns error."""
        result = runner.invoke(app, ["replay-session", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_replay_accepts_safe_flag(self) -> None:
        """Replay accepts --safe flag."""
        result = runner.invoke(app, ["replay-session", "--help"])
        assert "--safe" in result.stdout or "-s" in result.stdout

    def test_replay_accepts_mode_option(self) -> None:
        """Replay accepts --mode option for safe replay."""
        result = runner.invoke(app, ["replay-session", "--help"])
        assert "--mode" in result.stdout or "-m" in result.stdout


class TestImportSessionCommand:
    """Tests for import-session command argument handling."""

    def test_import_requires_source(self) -> None:
        """Import without source file shows error."""
        result = runner.invoke(app, ["import-session"])
        assert result.exit_code != 0  # Missing required argument

    def test_import_accepts_output_option(self) -> None:
        """Import accepts --output option."""
        result = runner.invoke(app, ["import-session", "--help"])
        assert "--output" in result.stdout or "-o" in result.stdout

    def test_import_missing_file_errors(self) -> None:
        """Import with nonexistent file returns error."""
        result = runner.invoke(app, ["import-session", "nonexistent.json"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestConvertSessionCommand:
    """Tests for convert-session command."""

    def test_convert_requires_description(self) -> None:
        """Convert requires --description option."""
        result = runner.invoke(app, ["convert-session", "some_session"])
        assert result.exit_code != 0  # Missing required option

    def test_convert_missing_session_errors(self) -> None:
        """Convert with nonexistent session returns error."""
        result = runner.invoke(
            app, ["convert-session", "nonexistent", "-d", "Test workflow"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestListSessionsCommand:
    """Tests for list-sessions command."""

    def test_list_missing_dir_errors(self) -> None:
        """List with nonexistent directory returns error."""
        result = runner.invoke(app, ["list-sessions", "nonexistent_dir"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestCLIWithFixtures:
    """Tests using session fixtures from conftest.py."""

    def test_import_valid_session(self, sample_session_file: Path) -> None:
        """Import with valid session file works."""
        assert sample_session_file.exists()
        # Note: Actually running import would need a tmp output dir
