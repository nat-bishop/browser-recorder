"""Network request models for captured HTTP traffic."""

from datetime import datetime

from pydantic import BaseModel, Field


class NetworkRequest(BaseModel):
    """HTTP request/response captured during recording.

    Based on HAR (HTTP Archive) format used by Playwright traces.
    """

    timestamp: datetime = Field(description="Request start time (UTC)")
    method: str = Field(description="HTTP method (GET, POST, etc.)")
    url: str = Field(description="Full request URL")
    status: int | None = Field(default=None, description="Response status code")
    status_text: str | None = Field(default=None, description="Response status text")
    duration_ms: float | None = Field(
        default=None, description="Request duration in ms"
    )
    mime_type: str | None = Field(default=None, description="Response MIME type")
    request_headers: dict[str, str] = Field(
        default_factory=dict, description="Request headers"
    )
    response_headers: dict[str, str] = Field(
        default_factory=dict, description="Response headers"
    )
    request_body_size: int | None = Field(
        default=None, description="Request body size in bytes"
    )
    response_body_size: int | None = Field(
        default=None, description="Response body size in bytes"
    )
