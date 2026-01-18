"""Cost projections endpoint for estimating remaining costs."""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ProjectionResponse(BaseModel):
    """Cost projection data for API response."""
    avg_cost_per_feature: float = 0.0
    features_remaining: int = 0
    features_completed: int = 0
    projected_remaining_cost_low: float = 0.0   # 75th percentile (optimistic)
    projected_remaining_cost_mid: float = 0.0   # median
    projected_remaining_cost_high: float = 0.0  # 25th percentile (pessimistic)
    daily_burn_rate_7d: float = 0.0
    estimated_completion_date_mid: Optional[str] = None
    total_spent: float = 0.0
    confidence: Literal["low", "medium", "high"] = "low"


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


def calculate_percentile(data: list[float], percentile: float) -> float:
    """Calculate the nth percentile of a data list."""
    if not data:
        return 0.0
    n = len(data)
    if n == 1:
        return data[0]

    sorted_data = sorted(data)
    k = (n - 1) * (percentile / 100)
    f = int(k)
    c = f + 1 if f + 1 < n else f

    if f == c:
        return sorted_data[f]

    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


@router.get("/projections", response_model=ProjectionResponse)
async def get_projections(request: Request) -> ProjectionResponse:
    """Get cost projections for remaining work."""
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    # Load data
    sessions = load_session_history(project_path)
    backlog = load_backlog(project_path)
    features = backlog.get("features", [])

    # Count features by status
    completed_features = [f for f in features if f.get("status") == "completed"]
    remaining_features = [
        f for f in features
        if f.get("status") in ("pending", "in_progress", "blocked")
    ]
    features_completed = len(completed_features)
    features_remaining = len(remaining_features)

    # Calculate total spent
    total_spent = sum(s.get("cost_usd", 0.0) for s in sessions)

    # Calculate cost per completed feature
    feature_costs: list[float] = []
    for feature in completed_features:
        feature_id = feature.get("id")
        if feature_id:
            feature_sessions = [
                s for s in sessions
                if s.get("feature_id") == feature_id
            ]
            if feature_sessions:
                cost = sum(s.get("cost_usd", 0.0) for s in feature_sessions)
                feature_costs.append(cost)

    # Calculate projections
    avg_cost_per_feature = 0.0
    projected_low = 0.0
    projected_mid = 0.0
    projected_high = 0.0

    if feature_costs:
        avg_cost_per_feature = statistics.mean(feature_costs)

        # Use percentiles for confidence interval
        # Low = 75th percentile (optimistic - assuming below average cost)
        # Mid = median
        # High = 25th percentile (pessimistic - assuming above average cost)
        cost_25th = calculate_percentile(feature_costs, 25)
        cost_50th = calculate_percentile(feature_costs, 50)
        cost_75th = calculate_percentile(feature_costs, 75)

        projected_low = cost_25th * features_remaining
        projected_mid = cost_50th * features_remaining
        projected_high = cost_75th * features_remaining

    # Calculate daily burn rate (last 7 days)
    now = datetime.now()
    seven_days_ago = now - timedelta(days=7)
    recent_sessions = [
        s for s in sessions
        if s.get("started_at") and
        datetime.fromisoformat(s["started_at"].replace("Z", "+00:00").replace("+00:00", "")) >= seven_days_ago
    ]
    recent_cost = sum(s.get("cost_usd", 0.0) for s in recent_sessions)
    daily_burn_rate = recent_cost / 7.0

    # Estimate completion date based on burn rate
    estimated_completion_date = None
    if daily_burn_rate > 0 and projected_mid > 0:
        days_remaining = projected_mid / daily_burn_rate
        completion = now + timedelta(days=days_remaining)
        estimated_completion_date = completion.strftime("%Y-%m-%d")

    # Determine confidence level based on sample size
    if len(feature_costs) >= 5:
        confidence = "high"
    elif len(feature_costs) >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return ProjectionResponse(
        avg_cost_per_feature=round(avg_cost_per_feature, 4),
        features_remaining=features_remaining,
        features_completed=features_completed,
        projected_remaining_cost_low=round(projected_low, 4),
        projected_remaining_cost_mid=round(projected_mid, 4),
        projected_remaining_cost_high=round(projected_high, 4),
        daily_burn_rate_7d=round(daily_burn_rate, 4),
        estimated_completion_date_mid=estimated_completion_date,
        total_spent=round(total_spent, 4),
        confidence=confidence,
    )
