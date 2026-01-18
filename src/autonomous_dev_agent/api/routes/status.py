"""Status endpoint for harness state."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class HarnessStatus(BaseModel):
    """Current status of the harness."""
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    is_running: bool = False
    current_feature_id: Optional[str] = None
    current_feature_name: Optional[str] = None
    current_session_id: Optional[str] = None
    context_usage_percent: float = 0.0
    total_sessions: int = 0
    features_completed: int = 0
    features_total: int = 0
    last_updated: Optional[datetime] = None


def get_project_path(request: Request) -> Optional[Path]:
    """Get project path from app state."""
    return getattr(request.app.state, "project_path", None)


@router.get("/status", response_model=HarnessStatus)
async def get_status(request: Request) -> HarnessStatus:
    """Get current harness status.

    Reads state from project files to determine current status.
    """
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        return HarnessStatus()

    status = HarnessStatus(project_path=str(project_path))

    # Try to load backlog for project info
    backlog_file = project_path / "feature-list.json"
    if backlog_file.exists():
        try:
            backlog_data = json.loads(backlog_file.read_text())
            status.project_name = backlog_data.get("project_name", project_path.name)

            features = backlog_data.get("features", [])
            status.features_total = len(features)
            status.features_completed = sum(
                1 for f in features if f.get("status") == "completed"
            )

            # Find current in-progress feature
            for f in features:
                if f.get("status") == "in_progress":
                    status.current_feature_id = f.get("id")
                    status.current_feature_name = f.get("name")
                    break

            status.last_updated = datetime.fromisoformat(
                backlog_data.get("last_updated", datetime.now().isoformat())
            )
        except (json.JSONDecodeError, Exception):
            pass

    # Try to load session state
    state_file = project_path / ".ada_session_state.json"
    if state_file.exists():
        try:
            state_data = json.loads(state_file.read_text())
            status.current_session_id = state_data.get("session_id")
            status.context_usage_percent = state_data.get("context_usage_percent", 0.0)
            status.is_running = True  # Session state exists = running
        except (json.JSONDecodeError, Exception):
            pass

    # Try to get session count from history
    history_file = project_path / ".ada_session_history.json"
    if history_file.exists():
        try:
            history_data = json.loads(history_file.read_text())
            if isinstance(history_data, list):
                status.total_sessions = len(history_data)
        except (json.JSONDecodeError, Exception):
            pass

    return status
