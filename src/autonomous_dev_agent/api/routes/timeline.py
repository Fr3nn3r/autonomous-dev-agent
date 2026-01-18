"""Timeline endpoint for feature Gantt view."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class SessionSegment(BaseModel):
    """A session segment in the timeline."""
    session_id: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    outcome: str = "success"
    cost_usd: float = 0.0


class FeatureTimelineEntry(BaseModel):
    """A feature entry in the timeline."""
    id: str
    name: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    sessions: list[SessionSegment] = []
    total_duration_hours: float = 0.0
    total_cost_usd: float = 0.0


class TimelineResponse(BaseModel):
    """Timeline data for API response."""
    features: list[FeatureTimelineEntry]
    earliest_start: Optional[str] = None
    latest_end: Optional[str] = None


def get_project_path(request: Request) -> Optional[Path]:
    """Get project path from app state."""
    return getattr(request.app.state, "project_path", None)


def load_session_history(project_path: Path) -> list[dict]:
    """Load session history from file."""
    history_file = project_path / ".ada_session_history.json"
    if not history_file.exists():
        return []

    try:
        data = json.loads(history_file.read_text())
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "sessions" in data:
            return data["sessions"]
        return []
    except json.JSONDecodeError:
        return []


def load_backlog(project_path: Path) -> dict:
    """Load backlog from file."""
    backlog_file = project_path / "feature-list.json"
    if not backlog_file.exists():
        return {"features": []}

    try:
        return json.loads(backlog_file.read_text())
    except json.JSONDecodeError:
        return {"features": []}


def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse datetime string to datetime object."""
    if not dt_str:
        return None
    try:
        # Handle various ISO formats
        clean_str = dt_str.replace("Z", "+00:00")
        if "+" in clean_str or "-" in clean_str[-6:]:
            # Has timezone info, strip it for naive datetime
            clean_str = clean_str.rsplit("+", 1)[0].rsplit("-", 1)[0]
        return datetime.fromisoformat(clean_str)
    except (ValueError, TypeError):
        return None


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(request: Request) -> TimelineResponse:
    """Get feature timeline data for Gantt view."""
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    # Load data
    sessions = load_session_history(project_path)
    backlog = load_backlog(project_path)
    features = backlog.get("features", [])

    # Group sessions by feature_id
    sessions_by_feature: dict[str, list[dict]] = {}
    for session in sessions:
        feature_id = session.get("feature_id")
        if feature_id:
            if feature_id not in sessions_by_feature:
                sessions_by_feature[feature_id] = []
            sessions_by_feature[feature_id].append(session)

    # Build timeline entries
    timeline_entries: list[FeatureTimelineEntry] = []
    all_starts: list[datetime] = []
    all_ends: list[datetime] = []

    for feature in features:
        feature_id = feature.get("id", "")
        feature_sessions = sessions_by_feature.get(feature_id, [])

        # Sort sessions by start time
        feature_sessions.sort(key=lambda s: s.get("started_at", ""))

        # Build session segments
        segments: list[SessionSegment] = []
        total_cost = 0.0
        total_duration_seconds = 0.0

        for session in feature_sessions:
            started_at = session.get("started_at")
            ended_at = session.get("ended_at")

            segment = SessionSegment(
                session_id=session.get("session_id", ""),
                started_at=started_at,
                ended_at=ended_at,
                outcome=session.get("outcome", "success"),
                cost_usd=session.get("cost_usd", 0.0),
            )
            segments.append(segment)
            total_cost += session.get("cost_usd", 0.0)

            # Calculate duration
            start_dt = parse_datetime(started_at)
            end_dt = parse_datetime(ended_at)
            if start_dt and end_dt:
                duration = (end_dt - start_dt).total_seconds()
                total_duration_seconds += duration

            # Track overall timeline bounds
            if start_dt:
                all_starts.append(start_dt)
            if end_dt:
                all_ends.append(end_dt)

        # Determine feature start/end times
        feature_started_at = feature.get("started_at")
        feature_completed_at = feature.get("completed_at")

        # If not in feature data, use session bounds
        if not feature_started_at and feature_sessions:
            first_session = feature_sessions[0]
            feature_started_at = first_session.get("started_at")

        if not feature_completed_at and feature_sessions:
            last_session = feature_sessions[-1]
            if feature.get("status") == "completed":
                feature_completed_at = last_session.get("ended_at")

        entry = FeatureTimelineEntry(
            id=feature_id,
            name=feature.get("name", ""),
            status=feature.get("status", "pending"),
            started_at=feature_started_at,
            completed_at=feature_completed_at,
            sessions=segments,
            total_duration_hours=round(total_duration_seconds / 3600, 2),
            total_cost_usd=round(total_cost, 4),
        )
        timeline_entries.append(entry)

    # Sort by started_at (features with sessions first, then by start time)
    def sort_key(entry: FeatureTimelineEntry) -> tuple:
        if entry.started_at:
            return (0, entry.started_at)
        else:
            return (1, entry.name)

    timeline_entries.sort(key=sort_key)

    # Calculate overall timeline bounds
    earliest_start = min(all_starts).isoformat() if all_starts else None
    latest_end = max(all_ends).isoformat() if all_ends else None

    return TimelineResponse(
        features=timeline_entries,
        earliest_start=earliest_start,
        latest_end=latest_end,
    )
