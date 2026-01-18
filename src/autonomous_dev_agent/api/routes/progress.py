"""Progress endpoint for reading progress log."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class ProgressResponse(BaseModel):
    """Progress log content."""
    content: str
    lines: int
    total_lines: int
    file_size_kb: float


def get_project_path(request: Request) -> Optional[Path]:
    """Get project path from app state."""
    return getattr(request.app.state, "project_path", None)


@router.get("/progress", response_model=ProgressResponse)
async def get_progress(
    request: Request,
    lines: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> ProgressResponse:
    """Get recent progress log entries.

    Args:
        lines: Number of lines to return (from end of file)
        offset: Skip this many lines from the end
    """
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    progress_file = project_path / "claude-progress.txt"
    if not progress_file.exists():
        return ProgressResponse(
            content="",
            lines=0,
            total_lines=0,
            file_size_kb=0.0,
        )

    try:
        content = progress_file.read_text()
        all_lines = content.strip().split("\n") if content.strip() else []
        total_lines = len(all_lines)
        file_size_kb = progress_file.stat().st_size / 1024

        # Get requested slice from end
        if offset > 0:
            end = -offset if offset < total_lines else 0
            start = max(0, end - lines) if end != 0 else max(0, total_lines - lines - offset)
            selected_lines = all_lines[start:end] if end != 0 else all_lines[start:]
        else:
            selected_lines = all_lines[-lines:] if lines < total_lines else all_lines

        return ProgressResponse(
            content="\n".join(selected_lines),
            lines=len(selected_lines),
            total_lines=total_lines,
            file_size_kb=round(file_size_kb, 2),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading progress file: {e}")


@router.get("/progress/full", response_model=ProgressResponse)
async def get_full_progress(request: Request) -> ProgressResponse:
    """Get the full progress log.

    Use with caution for large logs.
    """
    project_path = get_project_path(request)

    if not project_path or not project_path.exists():
        raise HTTPException(status_code=404, detail="Project path not configured")

    progress_file = project_path / "claude-progress.txt"
    if not progress_file.exists():
        return ProgressResponse(
            content="",
            lines=0,
            total_lines=0,
            file_size_kb=0.0,
        )

    try:
        content = progress_file.read_text()
        all_lines = content.strip().split("\n") if content.strip() else []
        file_size_kb = progress_file.stat().st_size / 1024

        return ProgressResponse(
            content=content,
            lines=len(all_lines),
            total_lines=len(all_lines),
            file_size_kb=round(file_size_kb, 2),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading progress file: {e}")
