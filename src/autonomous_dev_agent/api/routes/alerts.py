"""Alerts endpoint for notification management."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ...alert_manager import AlertManager

router = APIRouter()


class AlertResponse(BaseModel):
    """Alert data for API response."""
    id: str
    type: str
    severity: str
    title: str
    message: str
    timestamp: datetime
    read: bool
    dismissed: bool
    feature_id: Optional[str] = None
    session_id: Optional[str] = None


class AlertListResponse(BaseModel):
    """List of alerts."""
    alerts: list[AlertResponse]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """Unread alert count."""
    count: int


class SuccessResponse(BaseModel):
    """Success response."""
    success: bool
    message: str


def get_project_path(request: Request) -> Optional[Path]:
    """Get project path from app state."""
    return getattr(request.app.state, "project_path", None)


def get_alert_manager(request: Request) -> AlertManager:
    """Get or create AlertManager for the project."""
    project_path = get_project_path(request)
    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    # Cache the AlertManager in app state for efficiency
    if not hasattr(request.app.state, "_alert_manager"):
        request.app.state._alert_manager = AlertManager(
            project_path,
            enable_desktop_notifications=False  # API doesn't send desktop notifications
        )
    return request.app.state._alert_manager


@router.get("/alerts", response_model=AlertListResponse)
async def get_alerts(
    request: Request,
    include_dismissed: bool = False,
) -> AlertListResponse:
    """Get all alerts."""
    manager = get_alert_manager(request)
    alerts = manager.get_all_alerts(include_dismissed=include_dismissed)

    return AlertListResponse(
        alerts=[
            AlertResponse(
                id=a.id,
                type=a.type.value,
                severity=a.severity.value,
                title=a.title,
                message=a.message,
                timestamp=a.timestamp,
                read=a.read,
                dismissed=a.dismissed,
                feature_id=a.feature_id,
                session_id=a.session_id,
            )
            for a in alerts
        ],
        total=len(alerts),
        unread_count=manager.get_unread_count(),
    )


@router.get("/alerts/unread/count", response_model=UnreadCountResponse)
async def get_unread_count(request: Request) -> UnreadCountResponse:
    """Get count of unread alerts."""
    manager = get_alert_manager(request)
    return UnreadCountResponse(count=manager.get_unread_count())


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(request: Request, alert_id: str) -> AlertResponse:
    """Get a specific alert."""
    manager = get_alert_manager(request)
    alert = manager.get_alert(alert_id)

    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")

    return AlertResponse(
        id=alert.id,
        type=alert.type.value,
        severity=alert.severity.value,
        title=alert.title,
        message=alert.message,
        timestamp=alert.timestamp,
        read=alert.read,
        dismissed=alert.dismissed,
        feature_id=alert.feature_id,
        session_id=alert.session_id,
    )


@router.post("/alerts/{alert_id}/read", response_model=SuccessResponse)
async def mark_alert_read(request: Request, alert_id: str) -> SuccessResponse:
    """Mark an alert as read."""
    manager = get_alert_manager(request)
    success = manager.mark_read(alert_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")

    return SuccessResponse(success=True, message="Alert marked as read")


@router.post("/alerts/read-all", response_model=SuccessResponse)
async def mark_all_read(request: Request) -> SuccessResponse:
    """Mark all alerts as read."""
    manager = get_alert_manager(request)
    count = manager.mark_all_read()
    return SuccessResponse(success=True, message=f"Marked {count} alerts as read")


@router.post("/alerts/{alert_id}/dismiss", response_model=SuccessResponse)
async def dismiss_alert(request: Request, alert_id: str) -> SuccessResponse:
    """Dismiss an alert."""
    manager = get_alert_manager(request)
    success = manager.dismiss(alert_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")

    return SuccessResponse(success=True, message="Alert dismissed")


@router.post("/alerts/dismiss-all", response_model=SuccessResponse)
async def dismiss_all(request: Request) -> SuccessResponse:
    """Dismiss all alerts."""
    manager = get_alert_manager(request)
    count = manager.dismiss_all()
    return SuccessResponse(success=True, message=f"Dismissed {count} alerts")
