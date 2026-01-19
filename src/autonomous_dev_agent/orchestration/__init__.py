"""Orchestration components for the autonomous development agent.

This package contains the decomposed components of the harness orchestrator:
- SessionRecoveryManager: Handles signals, shutdown, and state persistence
- FeatureCompletionHandler: Manages verification, tests, and quality gates
- SessionOrchestrator: Controls session lifecycle, prompts, and execution

Together, these components implement the SOLID-compliant architecture
with clear separation of concerns and dependency injection support.
"""

from .recovery import SessionRecoveryManager
from .feature_completion import FeatureCompletionHandler
from .session_orchestrator import SessionOrchestrator

__all__ = [
    "SessionRecoveryManager",
    "FeatureCompletionHandler",
    "SessionOrchestrator",
]
