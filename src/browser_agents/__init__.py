"""Browser-agents: Record and replay browser interactions."""

__version__ = "0.1.0"

from browser_agents.models import (
    ActionDefinition,
    ActionParameter,
    ActionStep,
    RecordedEvent,
    Recording,
)

__all__ = [
    "ActionDefinition",
    "ActionParameter",
    "ActionStep",
    "RecordedEvent",
    "Recording",
    "__version__",
]
