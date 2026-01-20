"""Session recovery and shutdown management.

Handles:
- Signal handlers for graceful shutdown (SIGINT, SIGTERM)
- File-based stop signal detection
- State persistence for session recovery
- Graceful shutdown with auto-commit of uncommitted work
"""

import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel

from ..models import (
    HarnessConfig, Feature, ProgressEntry, SessionState
)
from ..protocols import GitOperations, ProgressLog

if TYPE_CHECKING:
    from ..session import SessionManager, BaseSession


console = Console()

# Stop request file path (relative to project directory)
STOP_REQUEST_FILE = ".ada/stop-requested"


class SessionRecoveryManager:
    """Manages session recovery and graceful shutdown.

    Single Responsibility: Handle shutdown signals, persist state,
    and recover interrupted sessions.

    Dependencies are injected for testability:
    - GitOperations: For committing uncommitted work on shutdown
    - ProgressLog: For logging shutdown events
    - SessionManager: For accessing recovery state
    """

    def __init__(
        self,
        config: HarnessConfig,
        project_path: Path,
        progress: ProgressLog,
        git: GitOperations,
        session_manager: "SessionManager",
    ):
        """Initialize the recovery manager.

        Args:
            config: Harness configuration
            project_path: Path to the project directory
            progress: Progress log for tracking events
            git: Git operations for status/commit
            session_manager: Session manager for recovery state
        """
        self.config = config
        self.project_path = Path(project_path)
        self.progress = progress
        self.git = git
        self.session_manager = session_manager

        # State
        self._shutdown_requested = False
        self._current_feature: Optional[Feature] = None
        self._current_session: Optional["BaseSession"] = None

    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown.

        On Windows, only SIGINT (Ctrl+C) is supported.
        On Unix, both SIGINT and SIGTERM are handled.
        """
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

        # SIGTERM is not available on Windows
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._handle_shutdown_signal)

    def _handle_shutdown_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal by setting flag.

        Args:
            signum: Signal number received
            frame: Current stack frame (unused)
        """
        signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        console.print(f"\n[yellow]Shutdown signal received ({signal_name}) - finishing current work...[/yellow]")
        self._shutdown_requested = True

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested.

        Checks both:
        1. Signal flag (from SIGINT/SIGTERM handlers)
        2. Stop request file (.ada/stop-requested)

        Returns:
            True if shutdown was requested via signal or file
        """
        if self._shutdown_requested:
            return True

        # Check for stop request file
        stop_file = self.project_path / STOP_REQUEST_FILE
        if stop_file.exists():
            console.print("[yellow]Stop request file detected...[/yellow]")
            self._shutdown_requested = True
            return True

        return False

    def request_stop(self, reason: str = "User requested stop") -> Path:
        """Create stop request file to signal graceful shutdown.

        Args:
            reason: Reason for the stop request

        Returns:
            Path to the created stop file
        """
        stop_file = self.project_path / STOP_REQUEST_FILE
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        stop_file.write_text(f"{datetime.now().isoformat()}\n{reason}")
        return stop_file

    def _clear_stop_request(self) -> None:
        """Remove stop request file after shutdown completes."""
        stop_file = self.project_path / STOP_REQUEST_FILE
        if stop_file.exists():
            try:
                stop_file.unlink()
                console.print("[dim]Cleared stop request file[/dim]")
            except OSError:
                pass  # File may have been removed already

    def set_current_context(
        self,
        feature: Optional[Feature] = None,
        session: Optional["BaseSession"] = None
    ) -> None:
        """Set the current feature and session for shutdown handling.

        Args:
            feature: Current feature being worked on
            session: Current active session
        """
        self._current_feature = feature
        self._current_session = session

    async def graceful_shutdown(
        self,
        current_feature: Optional[Feature] = None,
        current_session: Optional["BaseSession"] = None
    ) -> None:
        """Perform graceful shutdown - commit current work, save state, exit cleanly.

        Args:
            current_feature: Override current feature (uses stored if None)
            current_session: Override current session (uses stored if None)
        """
        console.print("\n[yellow]Performing graceful shutdown...[/yellow]")

        feature = current_feature or self._current_feature
        session = current_session or self._current_session

        # Commit any uncommitted changes
        git_status = self.git.get_status()
        commit_hash = None

        if git_status.has_changes:
            console.print("[yellow]Committing uncommitted changes...[/yellow]")
            self.git.stage_all()
            commit_hash = self.git.commit(
                "wip: interrupted by shutdown signal\n\n"
                "Auto-committed by autonomous-dev-agent during shutdown.\n"
                f"Feature in progress: {feature.name if feature else 'unknown'}"
            )
            if commit_hash:
                console.print(f"[green]Committed:[/green] {commit_hash[:8]}")

        # Log the shutdown
        session_id = session.session_id if session else "shutdown"
        self.progress.append_entry(ProgressEntry(
            session_id=session_id,
            feature_id=feature.id if feature else None,
            action="shutdown",
            summary="Graceful shutdown initiated by user signal",
            commit_hash=commit_hash
        ))

        # Save session state for recovery
        if session and feature:
            self.save_session_state(
                session,
                feature,
                handoff_notes="Session interrupted by shutdown signal"
            )
            console.print("[green]Session state saved for recovery[/green]")

        # Clean up stop request file if it exists
        self._clear_stop_request()

        console.print("[green]Shutdown complete.[/green]")

    def save_session_state(
        self,
        session: "BaseSession",
        feature: Feature,
        context_percent: float = 0.0,
        handoff_notes: Optional[str] = None
    ) -> None:
        """Save session state for recovery.

        Args:
            session: Current session
            feature: Feature being worked on
            context_percent: Current context usage percentage
            handoff_notes: Optional notes for the next session
        """
        state = SessionState(
            session_id=session.session_id,
            current_feature_id=feature.id,
            context_usage_percent=context_percent,
            last_commit_hash=self.git.get_status().last_commit_hash,
            handoff_notes=handoff_notes
        )
        session.save_state(state)

    async def check_for_recovery(self) -> Optional[str]:
        """Check for interrupted session and prompt for recovery.

        Returns:
            Feature ID to resume, or None to start fresh
        """
        recovery_state = self.session_manager.get_recovery_state()

        if not recovery_state:
            return None

        if not recovery_state.current_feature_id:
            # Clear stale state with no feature
            session = self.session_manager.create_session()
            session.clear_state()
            return None

        # Found interrupted session - display recovery info
        console.print(Panel(
            f"[yellow]Previous session interrupted[/yellow]\n"
            f"Session: {recovery_state.session_id}\n"
            f"Feature: {recovery_state.current_feature_id}\n"
            f"Context: {recovery_state.context_usage_percent:.1f}%\n"
            f"Started: {recovery_state.started_at}",
            title="Recovery"
        ))

        # For now, auto-resume (in future, could prompt user)
        console.print("[green]Resuming interrupted session...[/green]")
        return recovery_state.current_feature_id
