"""Clean models for browser recording sessions.

This package provides a clean architecture for browser automation:

Recording (raw events):
- events.py: UIEvent, UIEventType for user interactions
- session.py: RecordingSession, SessionMetadata, VideoInfo for sessions

Workflow (LLM-processed output):
- workflow.py: ActionDefinition, ActionStep, ActionParameter for reusable workflows
"""

from .events import UIEvent, UIEventType
from .network import NetworkRequest
from .session import RecordingSession, SessionMetadata, VideoInfo
from .workflow import (
    ActionDefinition,
    ActionParameter,
    ActionStep,
    StepAction,
)

__all__ = [
    # Events
    "UIEvent",
    "UIEventType",
    # Network
    "NetworkRequest",
    # Session
    "RecordingSession",
    "SessionMetadata",
    "VideoInfo",
    # Workflow
    "ActionDefinition",
    "ActionParameter",
    "ActionStep",
    "StepAction",
]
