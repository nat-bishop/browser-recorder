"""Playback utilities for replaying recorded sessions.

This package provides:
- SelectorResolver: Codegen-style selector resolution
- SessionExecutor: Session replay with fallback to coordinates
- SafeReplayMode: Network interception modes
- SafeReplayController: Block/mock state-changing requests
"""

from .executor import PlaybackError, SessionExecutor
from .safe_replay import SafeReplayController, SafeReplayMode
from .selector_resolver import SelectorResolver

__all__ = [
    "PlaybackError",
    "SafeReplayController",
    "SafeReplayMode",
    "SelectorResolver",
    "SessionExecutor",
]
