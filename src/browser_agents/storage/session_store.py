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
