"""Session models for recording browser sessions."""

from datetime import datetime

from pydantic import BaseModel, Field

from .events import UIEvent
from .network import NetworkRequest


class VideoInfo(BaseModel):
    """Video recording metadata."""

    path: str = Field(description="Relative path to video file")
    format: str = Field(default="webm", description="Video format (webm or mp4)")
    duration_ms: int | None = Field(
        default=None, description="Video duration in milliseconds"
    )
    start_offset_ms: int = Field(
        default=0, description="Offset from session start for sync (usually ~50ms)"
    )


class SessionMetadata(BaseModel):
    """Recording session metadata."""

    id: str = Field(description="Unique session identifier")
    version: int = Field(default=1, description="Schema version")

    # Timing
    started_at: datetime = Field(description="When recording started (UTC)")
    ended_at: datetime | None = Field(
        default=None, description="When recording ended (UTC)"
    )
    duration_ms: int | None = Field(default=None, description="Total session duration")

    # Source
    source_url: str = Field(description="Initial URL when recording started")

    # Browser context
    browser_name: str | None = Field(
        default=None, description="Browser name (Chrome, Firefox, etc.)"
    )
    browser_version: str | None = Field(default=None, description="Browser version")
    viewport_width: int | None = Field(
        default=None, description="Viewport width in pixels"
    )
    viewport_height: int | None = Field(
        default=None, description="Viewport height in pixels"
    )

    # Video
    video: VideoInfo | None = Field(default=None, description="Video recording info")

    # User-provided
    name: str | None = Field(default=None, description="Human-readable session name")
    description: str | None = Field(default=None, description="Session description")


class RecordingSession(BaseModel):
    """Complete recording session - stored as single JSON file.

    Storage layout:
        sessions/{id}/
            session.json         # This model
            media/
                recording.webm   # Video (optional)
            processed/
                workflow.json    # LLM-derived ActionDefinition
    """

    metadata: SessionMetadata = Field(description="Session metadata")
    events: list[UIEvent] = Field(
        default_factory=list, description="All UI events in order"
    )
    network_requests: list[NetworkRequest] = Field(
        default_factory=list, description="HTTP requests captured during recording"
    )
