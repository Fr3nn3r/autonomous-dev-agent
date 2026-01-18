"""Dashboard API for the Autonomous Dev Agent.

Provides REST endpoints and WebSocket connections for real-time monitoring.
"""

from .main import create_app, run_dashboard

__all__ = ["create_app", "run_dashboard"]
