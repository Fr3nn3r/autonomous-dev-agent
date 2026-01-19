"""Protocol definitions for dependency injection.

These protocols define the interfaces for core components, enabling:
- Loose coupling between components
- Easy testing via mock implementations
- Clear contracts for extensibility

Based on SOLID principles:
- D: Dependency Inversion - depend on abstractions, not concretions
- I: Interface Segregation - small, focused interfaces
"""

from typing import Protocol, Optional, runtime_checkable
from pathlib import Path

from .models import ProgressEntry, Feature, VerificationResult


@runtime_checkable
class GitOperations(Protocol):
    """Protocol for git operations.

    Abstracts git interactions to allow mocking in tests
    and potential alternative VCS implementations.
    """

    def is_git_repo(self) -> bool:
        """Check if the project is a git repository."""
        ...

    def get_status(self) -> "GitStatus":
        """Get current git status."""
        ...

    def stage_all(self) -> None:
        """Stage all changes."""
        ...

    def commit(self, message: str, allow_empty: bool = False) -> Optional[str]:
        """Create a commit and return the hash, or None if failed."""
        ...

    def get_changed_files(self, since_commit: Optional[str] = None) -> list[str]:
        """Get list of files changed since a commit (or all uncommitted)."""
        ...


@runtime_checkable
class ProgressLog(Protocol):
    """Protocol for progress tracking.

    Abstracts the progress file operations to enable different
    storage backends and easier testing.
    """

    def read_progress(self) -> str:
        """Read the full progress file for session context."""
        ...

    def read_recent(self, lines: int = 50) -> str:
        """Read only recent progress for context efficiency."""
        ...

    def append_entry(self, entry: ProgressEntry) -> None:
        """Append a progress entry to the file."""
        ...

    def log_handoff(
        self,
        session_id: str,
        feature_id: Optional[str],
        summary: str,
        files_changed: list[str],
        commit_hash: Optional[str] = None,
        next_steps: Optional[str] = None
    ) -> None:
        """Log a handoff to the next session."""
        ...

    def log_feature_completed(
        self,
        session_id: str,
        feature: Feature,
        summary: str,
        commit_hash: Optional[str] = None
    ) -> None:
        """Log completion of a feature."""
        ...

    def log_session_start(
        self,
        session_id: str,
        feature: Optional[Feature] = None
    ) -> None:
        """Log the start of a new session."""
        ...

    def initialize(self, project_name: str) -> None:
        """Initialize a new progress file for a project."""
        ...


@runtime_checkable
class CommandExecutor(Protocol):
    """Protocol for executing shell commands.

    Abstracts command execution for testability and
    potential sandboxing/security features.
    """

    def run_command(
        self,
        name: str,
        command: Optional[str],
        timeout: int,
        env: Optional[dict] = None,
        shell: bool = True
    ) -> VerificationResult:
        """Execute a shell command and return the result.

        Args:
            name: Name of the command for logging/display
            command: The command to execute (None skips execution)
            timeout: Timeout in seconds
            env: Optional environment variables
            shell: Whether to run in shell mode

        Returns:
            VerificationResult with passed status and output
        """
        ...


# Re-export GitStatus for type hints
# This import is deferred to avoid circular imports
def _get_git_status_type():
    """Get GitStatus type for runtime use."""
    from .git_manager import GitStatus
    return GitStatus


# Type alias for use in annotations (forward reference)
GitStatus = "GitStatus"
