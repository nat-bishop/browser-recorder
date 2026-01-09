"""Session storage for loading and saving recording sessions."""

from pathlib import Path

from browser_agents.models import RecordingSession


class SessionStore:
    """Simple session storage - read/write JSON files.

    Storage layout:
        sessions/
        └── {session_id}/
            ├── session.json         # RecordingSession
            ├── media/
            │   └── recording.webm   # Video (optional)
            └── processed/
                └── workflow.json    # LLM-derived ActionDefinition
    """

    def __init__(self, base_path: Path | str = "sessions") -> None:
        """Initialize the session store.

        Args:
            base_path: Base directory for session storage.
        """
        self.base_path = Path(base_path)

    def load_session(self, session_id: str) -> RecordingSession:
        """Load a recording session by ID.

        Args:
            session_id: The session ID to load.

        Returns:
            The loaded RecordingSession.

        Raises:
            FileNotFoundError: If the session doesn't exist.
            ValidationError: If the session JSON is invalid.
        """
        session_path = self.base_path / session_id / "session.json"
        if not session_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        content = session_path.read_text(encoding="utf-8")
        return RecordingSession.model_validate_json(content)

    def save_session(self, session: RecordingSession) -> Path:
        """Save a recording session.

        Args:
            session: The session to save.

        Returns:
            Path to the saved session.json file.
        """
        session_dir = self.base_path / session.metadata.id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create media directory
        (session_dir / "media").mkdir(exist_ok=True)

        # Save session JSON
        session_path = session_dir / "session.json"
        session_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

        return session_path

    def list_sessions(self) -> list[str]:
        """List all session IDs.

        Returns:
            List of session ID strings.
        """
        if not self.base_path.exists():
            return []

        sessions = []
        for path in self.base_path.iterdir():
            if path.is_dir() and (path / "session.json").exists():
                sessions.append(path.name)

        return sorted(sessions, reverse=True)  # Most recent first (by name)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its files.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if deleted, False if session didn't exist.
        """
        import shutil

        session_dir = self.base_path / session_id
        if not session_dir.exists():
            return False

        shutil.rmtree(session_dir)
        return True

    def get_session_path(self, session_id: str) -> Path:
        """Get the directory path for a session.

        Args:
            session_id: The session ID.

        Returns:
            Path to the session directory.
        """
        return self.base_path / session_id

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: The session ID to check.

        Returns:
            True if the session exists.
        """
        return (self.base_path / session_id / "session.json").exists()
