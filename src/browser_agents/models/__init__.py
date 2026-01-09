"""Clean models for browser recording sessions.

This package provides a clean architecture for browser automation:

Recording (raw events):
- selectors.py: SelectorCandidate for Codegen-style element identification
- events.py: UIEvent, UIEventType for user interactions
- session.py: RecordingSession, SessionMetadata, VideoInfo for sessions

Workflow (LLM-processed output):
- workflow.py: ActionDefinition, ActionStep, ActionParameter for reusable workflows
"""

from .events import UIEvent, UIEventType
from .selectors import SelectorCandidate
from .session import RecordingSession, SessionMetadata, VideoInfo
from .workflow import (
    ActionDefinition,
    ActionParameter,
    ActionStep,
    ErrorDiagnosis,
    MediaRefs,
    ProposedFix,
    StepAction,
    StepFixSuggestion,
    SuccessCondition,
)

__all__ = [
    # Selectors
    "SelectorCandidate",
    # Events
    "UIEvent",
    "UIEventType",
    # Session
    "RecordingSession",
    "SessionMetadata",
    "VideoInfo",
    # Workflow
    "ActionDefinition",
    "ActionParameter",
    "ActionStep",
    "StepAction",
    # Error diagnosis
    "ErrorDiagnosis",
    "ProposedFix",
    "StepFixSuggestion",
    # Supporting
    "MediaRefs",
    "SuccessCondition",
]
