"""FastAPI application for the dashboard backend.

Provides REST API and WebSocket endpoints for real-time monitoring
of the autonomous development agent.
"""

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import status, backlog, sessions, progress, projections, timeline, alerts, control
from .websocket import router as websocket_router


def create_app(project_path: Optional[Path] = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        project_path: Path to the project being monitored

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="ADA Dashboard API",
        description="Real-time monitoring for Autonomous Dev Agent",
        version="0.6.0",
    )

    # Add CORS middleware for frontend access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store project path in app state
    app.state.project_path = project_path

    # Include routers
    app.include_router(status.router, prefix="/api", tags=["status"])
    app.include_router(backlog.router, prefix="/api", tags=["backlog"])
    app.include_router(sessions.router, prefix="/api", tags=["sessions"])
    app.include_router(progress.router, prefix="/api", tags=["progress"])
    app.include_router(projections.router, prefix="/api", tags=["projections"])
    app.include_router(timeline.router, prefix="/api", tags=["timeline"])
    app.include_router(alerts.router, prefix="/api", tags=["alerts"])
    app.include_router(control.router, prefix="/api", tags=["control"])
    app.include_router(websocket_router, prefix="/ws", tags=["websocket"])

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "ADA Dashboard API",
            "version": "0.5.0",
            "docs": "/docs",
        }

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


def run_dashboard(
    project_path: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False
) -> None:
    """Run the dashboard server.

    Args:
        project_path: Path to the project being monitored
        host: Host to bind to
        port: Port to listen on
        reload: Enable auto-reload for development
    """
    import uvicorn

    # Create app with project path
    app = create_app(project_path)

    # Run the server
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
    )


# Default app instance for uvicorn (e.g., uvicorn ...main:app)
app = create_app()


async def run_dashboard_async(
    project_path: Path,
    host: str = "127.0.0.1",
    port: int = 8000
) -> None:
    """Run the dashboard server asynchronously.

    Args:
        project_path: Path to the project being monitored
        host: Host to bind to
        port: Port to listen on
    """
    import uvicorn

    app = create_app(project_path)

    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()
