"""Control endpoints for stopping and managing the agent."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel


router = APIRouter()

# Stop request file path (must match recovery.py)
STOP_REQUEST_FILE = ".ada/stop-requested"


class StopRequest(BaseModel):
    """Request body for stop endpoint."""
    reason: Optional[str] = "Stop requested via API"


class StopResponse(BaseModel):
    """Response for stop request."""
    success: bool
    message: str
    stop_file: str


class StopStatus(BaseModel):
    """Response for stop status check."""
    stop_requested: bool
    stop_file: Optional[str] = None
    requested_at: Optional[str] = None
    reason: Optional[str] = None


def get_project_path(request: Request) -> Optional[Path]:
    """Get project path from app state."""
    return getattr(request.app.state, "project_path", None)


@router.post("/control/stop", response_model=StopResponse)
async def request_stop(request: Request, body: StopRequest = StopRequest()):
    """Request graceful shutdown of the running agent.

    Creates a stop request file that the agent checks after each tool call.
    The agent will finish its current work, commit changes, and exit cleanly.
    """
    project_path = get_project_path(request)

    if not project_path:
        raise HTTPException(status_code=400, detail="No project path configured")

    stop_file = project_path / STOP_REQUEST_FILE
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text(f"{datetime.now().isoformat()}\n{body.reason}")

    return StopResponse(
        success=True,
        message="Stop request sent. Agent will stop after current operation.",
        stop_file=str(stop_file)
    )


@router.get("/control/stop-status", response_model=StopStatus)
async def get_stop_status(request: Request):
    """Check if a stop has been requested.

    Returns the current stop status and details if a stop is pending.
    """
    project_path = get_project_path(request)

    if not project_path:
        raise HTTPException(status_code=400, detail="No project path configured")

    stop_file = project_path / STOP_REQUEST_FILE

    if not stop_file.exists():
        return StopStatus(stop_requested=False)

    # Parse stop file content
    content = stop_file.read_text().strip().split('\n')
    requested_at = content[0] if content else None
    reason = content[1] if len(content) > 1 else None

    return StopStatus(
        stop_requested=True,
        stop_file=str(stop_file),
        requested_at=requested_at,
        reason=reason
    )


@router.delete("/control/stop")
async def cancel_stop(request: Request):
    """Cancel a pending stop request.

    Removes the stop request file, allowing the agent to continue running.
    """
    project_path = get_project_path(request)

    if not project_path:
        raise HTTPException(status_code=400, detail="No project path configured")

    stop_file = project_path / STOP_REQUEST_FILE

    if stop_file.exists():
        stop_file.unlink()
        return {"success": True, "message": "Stop request cancelled"}

    return {"success": False, "message": "No stop request was pending"}
