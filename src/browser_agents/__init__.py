"""Browser-agents: Record and replay browser interactions."""

__version__ = "0.1.0"

from browser_agents.models import (
    ActionDefinition,
    ActionParameter,
    ActionStep,
    RecordingSession,
    SelectorCandidate,
    SessionMetadata,
    UIEvent,
    UIEventType,
)

__all__ = [
    "ActionDefinition",
    "ActionParameter",
    "ActionStep",
    "RecordingSession",
    "SelectorCandidate",
    "SessionMetadata",
    "UIEvent",
    "UIEventType",
    "__version__",
]
