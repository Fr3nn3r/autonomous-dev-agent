"""Sessions endpoint for session history and costs."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class SessionResponse(BaseModel):
    """Session record for API response."""
    session_id: str
    feature_id: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    outcome: str = "success"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str = ""
    cost_usd: float = 0.0
    files_changed: list[str] = []
    commit_hash: Optional[str] = None
    error_message: Optional[str] = None
    error_category: Optional[str] = None


class CostSummaryResponse(BaseModel):
    """Cost summary for API response."""
    total_cost_usd: float = 0.0
    total_sessions: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    cost_by_model: dict[str, float] = {}
    sessions_by_model: dict[str, int] = {}
    sessions_by_outcome: dict[str, int] = {}
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class SessionListResponse(BaseModel):
    """List of sessions with pagination info."""
    sessions: list[SessionResponse]
    total: int
    page: int
    page_size: int


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


@router.get("/sessions", response_model=SessionListResponse)
async def get_sessions(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    feature_id: Optional[str] = None,
    outcome: Optional[str] = None,
) -> SessionListResponse:
    """Get session history with optional filtering."""
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    records = load_session_history(project_path)

    # Apply filters
    if feature_id:
        records = [r for r in records if r.get("feature_id") == feature_id]
    if outcome:
        records = [r for r in records if r.get("outcome") == outcome]

    # Sort by started_at (newest first)
    records.sort(key=lambda r: r.get("started_at", ""), reverse=True)

    # Paginate
    total = len(records)
    start = (page - 1) * page_size
    end = start + page_size
    page_records = records[start:end]

    sessions = [
        SessionResponse(
            session_id=r.get("session_id", ""),
            feature_id=r.get("feature_id"),
            started_at=datetime.fromisoformat(r["started_at"]) if r.get("started_at") else None,
            ended_at=datetime.fromisoformat(r["ended_at"]) if r.get("ended_at") else None,
            outcome=r.get("outcome", "success"),
            input_tokens=r.get("input_tokens", 0),
            output_tokens=r.get("output_tokens", 0),
            cache_read_tokens=r.get("cache_read_tokens", 0),
            cache_write_tokens=r.get("cache_write_tokens", 0),
            model=r.get("model", ""),
            cost_usd=r.get("cost_usd", 0.0),
            files_changed=r.get("files_changed", []),
            commit_hash=r.get("commit_hash"),
            error_message=r.get("error_message"),
            error_category=r.get("error_category"),
        )
        for r in page_records
    ]

    return SessionListResponse(
        sessions=sessions,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sessions/costs", response_model=CostSummaryResponse)
async def get_cost_summary(
    request: Request,
    days: Optional[int] = Query(None, ge=1, le=365),
) -> CostSummaryResponse:
    """Get cost summary, optionally filtered by time period."""
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    records = load_session_history(project_path)

    # Filter by date if specified
    if days:
        cutoff = datetime.now() - timedelta(days=days)
        records = [
            r for r in records
            if r.get("started_at") and datetime.fromisoformat(r["started_at"]) >= cutoff
        ]

    # Aggregate
    summary = CostSummaryResponse(
        period_start=datetime.now() - timedelta(days=days) if days else None,
        period_end=datetime.now(),
    )

    for r in records:
        summary.total_sessions += 1
        summary.total_cost_usd += r.get("cost_usd", 0.0)
        summary.total_input_tokens += r.get("input_tokens", 0)
        summary.total_output_tokens += r.get("output_tokens", 0)
        summary.total_cache_read_tokens += r.get("cache_read_tokens", 0)
        summary.total_cache_write_tokens += r.get("cache_write_tokens", 0)

        model = r.get("model", "unknown")
        if model:
            summary.cost_by_model[model] = summary.cost_by_model.get(model, 0.0) + r.get("cost_usd", 0.0)
            summary.sessions_by_model[model] = summary.sessions_by_model.get(model, 0) + 1

        outcome = r.get("outcome", "unknown")
        summary.sessions_by_outcome[outcome] = summary.sessions_by_outcome.get(outcome, 0) + 1

    return summary


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(request: Request, session_id: str) -> SessionResponse:
    """Get a specific session by ID."""
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    records = load_session_history(project_path)

    for r in records:
        if r.get("session_id") == session_id:
            return SessionResponse(
                session_id=r.get("session_id", ""),
                feature_id=r.get("feature_id"),
                started_at=datetime.fromisoformat(r["started_at"]) if r.get("started_at") else None,
                ended_at=datetime.fromisoformat(r["ended_at"]) if r.get("ended_at") else None,
                outcome=r.get("outcome", "success"),
                input_tokens=r.get("input_tokens", 0),
                output_tokens=r.get("output_tokens", 0),
                cache_read_tokens=r.get("cache_read_tokens", 0),
                cache_write_tokens=r.get("cache_write_tokens", 0),
                model=r.get("model", ""),
                cost_usd=r.get("cost_usd", 0.0),
                files_changed=r.get("files_changed", []),
                commit_hash=r.get("commit_hash"),
                error_message=r.get("error_message"),
                error_category=r.get("error_category"),
            )

    raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
