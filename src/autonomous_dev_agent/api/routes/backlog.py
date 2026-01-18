"""Backlog endpoint for feature list."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class FeatureResponse(BaseModel):
    """Feature data for API response."""
    id: str
    name: str
    description: str
    category: str = "functional"
    status: str = "pending"
    priority: int = 0
    sessions_spent: int = 0
    depends_on: list[str] = []
    acceptance_criteria: list[str] = []
    implementation_notes: list[str] = []
    model_override: Optional[str] = None


class BacklogResponse(BaseModel):
    """Backlog data for API response."""
    project_name: str
    project_path: str
    features: list[FeatureResponse]
    total_features: int
    completed_features: int
    in_progress_features: int
    pending_features: int
    blocked_features: int


def get_project_path(request: Request) -> Optional[Path]:
    """Get project path from app state."""
    return getattr(request.app.state, "project_path", None)


@router.get("/backlog", response_model=BacklogResponse)
async def get_backlog(request: Request) -> BacklogResponse:
    """Get the full feature backlog."""
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    backlog_file = project_path / "feature-list.json"
    if not backlog_file.exists():
        raise HTTPException(status_code=404, detail="Backlog file not found")

    try:
        backlog_data = json.loads(backlog_file.read_text())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid backlog JSON: {e}")

    features = [
        FeatureResponse(
            id=f.get("id", ""),
            name=f.get("name", ""),
            description=f.get("description", ""),
            category=f.get("category", "functional"),
            status=f.get("status", "pending"),
            priority=f.get("priority", 0),
            sessions_spent=f.get("sessions_spent", 0),
            depends_on=f.get("depends_on", []),
            acceptance_criteria=f.get("acceptance_criteria", []),
            implementation_notes=f.get("implementation_notes", []),
            model_override=f.get("model_override"),
        )
        for f in backlog_data.get("features", [])
    ]

    # Count by status
    status_counts = {
        "completed": 0,
        "in_progress": 0,
        "pending": 0,
        "blocked": 0,
    }
    for f in features:
        if f.status in status_counts:
            status_counts[f.status] += 1

    return BacklogResponse(
        project_name=backlog_data.get("project_name", project_path.name),
        project_path=str(project_path),
        features=features,
        total_features=len(features),
        completed_features=status_counts["completed"],
        in_progress_features=status_counts["in_progress"],
        pending_features=status_counts["pending"],
        blocked_features=status_counts["blocked"],
    )


@router.get("/backlog/{feature_id}", response_model=FeatureResponse)
async def get_feature(request: Request, feature_id: str) -> FeatureResponse:
    """Get a specific feature by ID."""
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    backlog_file = project_path / "feature-list.json"
    if not backlog_file.exists():
        raise HTTPException(status_code=404, detail="Backlog file not found")

    try:
        backlog_data = json.loads(backlog_file.read_text())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid backlog JSON: {e}")

    for f in backlog_data.get("features", []):
        if f.get("id") == feature_id:
            return FeatureResponse(
                id=f.get("id", ""),
                name=f.get("name", ""),
                description=f.get("description", ""),
                category=f.get("category", "functional"),
                status=f.get("status", "pending"),
                priority=f.get("priority", 0),
                sessions_spent=f.get("sessions_spent", 0),
                depends_on=f.get("depends_on", []),
                acceptance_criteria=f.get("acceptance_criteria", []),
                implementation_notes=f.get("implementation_notes", []),
                model_override=f.get("model_override"),
            )

    raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")
