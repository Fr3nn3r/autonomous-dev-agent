"""WebSocket support for real-time updates.

Provides WebSocket connections for live dashboard updates.
Events are emitted when:
- Session starts/completes
- Feature status changes
- Cost updates occur
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for broadcasting events."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)

    async def broadcast(self, event: str, data: dict):
        """Broadcast an event to all connected clients.

        Args:
            event: Event type (e.g., "session.started")
            data: Event data payload
        """
        message = json.dumps({
            "event": event,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, event: str, data: dict):
        """Send an event to a specific client.

        Args:
            websocket: Target WebSocket connection
            event: Event type
            data: Event data payload
        """
        message = json.dumps({
            "event": event,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
        await websocket.send_text(message)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint for real-time events.

    Clients can connect to receive live updates about:
    - session.started - A new session has started
    - session.completed - A session has completed
    - feature.started - Work on a feature has started
    - feature.completed - A feature has been completed
    - cost.update - Cost data has been updated
    - progress.update - Progress log has new entries
    """
    await manager.connect(websocket)

    try:
        # Send initial connection confirmation
        await manager.send_personal(websocket, "connected", {
            "message": "Connected to ADA Dashboard events",
            "client_count": len(manager.active_connections)
        })

        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()

            try:
                message = json.loads(data)

                # Handle ping/pong
                if message.get("type") == "ping":
                    await manager.send_personal(websocket, "pong", {})

                # Handle subscription requests (for future use)
                elif message.get("type") == "subscribe":
                    events = message.get("events", [])
                    await manager.send_personal(websocket, "subscribed", {
                        "events": events
                    })

            except json.JSONDecodeError:
                # Ignore invalid JSON
                pass

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


# Event emission functions for use by the harness
async def emit_session_started(session_id: str, feature_id: Optional[str], model: str):
    """Emit session started event.

    Args:
        session_id: ID of the started session
        feature_id: ID of the feature being worked on
        model: Model being used
    """
    await manager.broadcast("session.started", {
        "session_id": session_id,
        "feature_id": feature_id,
        "model": model,
    })


async def emit_session_completed(
    session_id: str,
    feature_id: Optional[str],
    outcome: str,
    cost_usd: float,
    input_tokens: int,
    output_tokens: int
):
    """Emit session completed event.

    Args:
        session_id: ID of the completed session
        feature_id: ID of the feature worked on
        outcome: How the session ended
        cost_usd: Session cost
        input_tokens: Input tokens used
        output_tokens: Output tokens generated
    """
    await manager.broadcast("session.completed", {
        "session_id": session_id,
        "feature_id": feature_id,
        "outcome": outcome,
        "cost_usd": cost_usd,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    })


async def emit_feature_started(feature_id: str, feature_name: str):
    """Emit feature started event.

    Args:
        feature_id: ID of the feature
        feature_name: Name of the feature
    """
    await manager.broadcast("feature.started", {
        "feature_id": feature_id,
        "feature_name": feature_name,
    })


async def emit_feature_completed(feature_id: str, feature_name: str, sessions_spent: int):
    """Emit feature completed event.

    Args:
        feature_id: ID of the feature
        feature_name: Name of the feature
        sessions_spent: Total sessions spent on this feature
    """
    await manager.broadcast("feature.completed", {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "sessions_spent": sessions_spent,
    })


async def emit_cost_update(
    total_cost_usd: float,
    total_sessions: int,
    total_input_tokens: int,
    total_output_tokens: int
):
    """Emit cost update event.

    Args:
        total_cost_usd: Running total cost
        total_sessions: Total sessions run
        total_input_tokens: Total input tokens
        total_output_tokens: Total output tokens
    """
    await manager.broadcast("cost.update", {
        "total_cost_usd": total_cost_usd,
        "total_sessions": total_sessions,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
    })


async def emit_progress_update(entry: str):
    """Emit progress log update event.

    Args:
        entry: New progress log entry
    """
    await manager.broadcast("progress.update", {
        "entry": entry,
    })


async def emit_alert(
    alert_id: str,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    feature_id: Optional[str] = None,
    session_id: Optional[str] = None
):
    """Emit new alert event.

    Args:
        alert_id: Unique alert identifier
        alert_type: Type of alert
        severity: Alert severity level
        title: Alert title
        message: Alert message
        feature_id: Related feature ID
        session_id: Related session ID
    """
    await manager.broadcast("alert.new", {
        "id": alert_id,
        "type": alert_type,
        "severity": severity,
        "title": title,
        "message": message,
        "feature_id": feature_id,
        "session_id": session_id,
    })


class FileWatcher:
    """Watches project files for changes and emits events.

    This is a simple polling-based watcher. For production,
    consider using watchdog or similar for efficiency.
    """

    def __init__(self, project_path: Path, poll_interval: float = 1.0):
        """Initialize the file watcher.

        Args:
            project_path: Path to the project directory
            poll_interval: Seconds between file checks
        """
        self.project_path = project_path
        self.poll_interval = poll_interval
        self._running = False
        self._last_mtime: dict[str, float] = {}

    async def start(self):
        """Start watching for file changes."""
        self._running = True

        files_to_watch = [
            "feature-list.json",
            ".ada_session_state.json",
            ".ada_session_history.json",
            "claude-progress.txt",
            ".ada_alerts.json",
        ]

        # Initialize last modification times
        for filename in files_to_watch:
            filepath = self.project_path / filename
            if filepath.exists():
                self._last_mtime[filename] = filepath.stat().st_mtime

        while self._running:
            await asyncio.sleep(self.poll_interval)

            for filename in files_to_watch:
                filepath = self.project_path / filename
                if not filepath.exists():
                    continue

                current_mtime = filepath.stat().st_mtime
                last_mtime = self._last_mtime.get(filename, 0)

                if current_mtime > last_mtime:
                    self._last_mtime[filename] = current_mtime

                    # Emit appropriate event based on file
                    if filename == "feature-list.json":
                        await manager.broadcast("backlog.updated", {
                            "file": filename
                        })
                    elif filename == ".ada_session_history.json":
                        await manager.broadcast("sessions.updated", {
                            "file": filename
                        })
                    elif filename == "claude-progress.txt":
                        await manager.broadcast("progress.updated", {
                            "file": filename
                        })
                    elif filename == ".ada_session_state.json":
                        await manager.broadcast("status.updated", {
                            "file": filename
                        })
                    elif filename == ".ada_alerts.json":
                        await manager.broadcast("alerts.updated", {
                            "file": filename
                        })

    def stop(self):
        """Stop watching for file changes."""
        self._running = False


# Global file watcher instance
_file_watcher: Optional[FileWatcher] = None


async def start_file_watcher(project_path: Path):
    """Start the file watcher for a project.

    Args:
        project_path: Path to the project to watch
    """
    global _file_watcher

    if _file_watcher:
        _file_watcher.stop()

    _file_watcher = FileWatcher(project_path)
    asyncio.create_task(_file_watcher.start())


def stop_file_watcher():
    """Stop the file watcher."""
    global _file_watcher

    if _file_watcher:
        _file_watcher.stop()
        _file_watcher = None
