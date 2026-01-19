"""Main harness orchestrator for autonomous development.

This is the core engine that:
1. Loads the backlog
2. Runs initialization (first time only)
3. Loops through sessions until backlog is complete
4. Handles handoffs between sessions

Refactored following SOLID principles:
- Single Responsibility: Core coordination only, delegates to focused components
- Open/Closed: Extensible through dependency injection
- Dependency Inversion: Depends on protocols, not concrete implementations
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Optional, List, Tuple

from rich.console import Console
from rich.panel import Panel

from .models import (
    Backlog, Feature, FeatureStatus, HarnessConfig,
    ProgressEntry, ErrorCategory
)
from .progress import ProgressTracker
from .git_manager import GitManager
from .session import SessionManager, BaseSession, SessionResult
from .cost_tracker import CostTracker
from .session_history import SessionHistory
from .model_selector import ModelSelector
from .alert_manager import AlertManager
from .workspace import WorkspaceManager

# Import orchestration components
from .orchestration import (
    SessionOrchestrator,
    FeatureCompletionHandler,
    SessionRecoveryManager,
)

# Import protocols for type hints
from .protocols import GitOperations, ProgressLog


# Windows-compatible symbols (cp1252 doesn't support Unicode checkmarks)
if sys.platform == "win32":
    SYM_OK = "[OK]"
    SYM_FAIL = "[X]"
    SYM_WARN = "[!]"
else:
    SYM_OK = "✓"
    SYM_FAIL = "✗"
    SYM_WARN = "!"

console = Console()


class AutonomousHarness:
    """Main orchestrator for long-running autonomous development.

    Based on Anthropic's two-agent pattern:
    - Initializer agent sets up environment once
    - Coding agent makes incremental progress per session
    - Clean handoffs enable arbitrary-length development

    Follows SOLID principles with dependency injection for testability.
    """

    def __init__(
        self,
        project_path: str | Path,
        config: Optional[HarnessConfig] = None,
        # Optional DI for testing
        git: Optional[GitOperations] = None,
        progress: Optional[ProgressLog] = None,
        session_manager: Optional[SessionManager] = None,
        session_orchestrator: Optional[SessionOrchestrator] = None,
        completion_handler: Optional[FeatureCompletionHandler] = None,
        recovery_manager: Optional[SessionRecoveryManager] = None,
    ):
        """Initialize the harness with optional dependency injection.

        Args:
            project_path: Path to the project directory
            config: Harness configuration (uses defaults if None)
            git: Git operations (creates default if None)
            progress: Progress tracker (creates default if None)
            session_manager: Session manager (creates default if None)
            session_orchestrator: Session orchestrator (creates default if None)
            completion_handler: Feature completion handler (creates default if None)
            recovery_manager: Session recovery manager (creates default if None)
        """
        self.project_path = Path(project_path).resolve()
        self.config = config or HarnessConfig()

        # Core components - use injected or create defaults
        self.git = git or GitManager(self.project_path)
        self.progress = progress or ProgressTracker(
            self.project_path,
            self.config.progress_file,
            rotation_threshold_kb=self.config.progress_rotation_threshold_kb,
            keep_entries=self.config.progress_keep_entries
        )
        self.sessions = session_manager or SessionManager(self.config, self.project_path)

        # Supporting components (always created fresh)
        self.session_history = SessionHistory(self.project_path)
        self.cost_tracker = CostTracker(self.config.model)
        self.model_selector = ModelSelector(default_model=self.config.model)
        self.alert_manager = AlertManager(self.project_path, enable_desktop_notifications=True)

        # Observability workspace
        self.workspace = WorkspaceManager(self.project_path)
        self.workspace.ensure_structure()

        # Create orchestration components with dependencies
        self._completion_handler = completion_handler or FeatureCompletionHandler(
            config=self.config,
            project_path=self.project_path,
            progress=self.progress,
            git=self.git,
            alert_manager=self.alert_manager,
            session_history=self.session_history,
            backlog_saver=self.save_backlog,
        )

        self._recovery_manager = recovery_manager or SessionRecoveryManager(
            config=self.config,
            project_path=self.project_path,
            progress=self.progress,
            git=self.git,
            session_manager=self.sessions,
        )

        self._orchestrator = session_orchestrator or SessionOrchestrator(
            config=self.config,
            project_path=self.project_path,
            progress=self.progress,
            git=self.git,
            session_manager=self.sessions,
            workspace=self.workspace,
            model_selector=self.model_selector,
            alert_manager=self.alert_manager,
            session_history=self.session_history,
        )

        # Wire up circular dependencies between orchestration components
        self._orchestrator.set_completion_handler(self._completion_handler)
        self._orchestrator.set_recovery_manager(self._recovery_manager)

        # State
        self.backlog: Optional[Backlog] = None
        self.initialized = False
        self.total_sessions = 0

    async def _run_health_checks(self) -> Tuple[List[str], List[str]]:
        """Run pre-flight health checks.

        Returns:
            Tuple of (fatal_errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []

        console.print("\n[blue]Running health checks...[/blue]")

        # 1. Check if git repo exists
        if not self.git.is_git_repo():
            errors.append("Not a git repository")
        else:
            console.print(f"  [green]{SYM_OK}[/green] Git repository found")

            # Check for uncommitted changes
            git_status = self.git.get_status()
            if git_status.has_changes:
                warnings.append(
                    f"Uncommitted changes: {len(git_status.modified_files)} modified, "
                    f"{len(git_status.untracked_files)} untracked"
                )

        # 2. Check Claude CLI
        claude_path = shutil.which("claude")
        if not claude_path and sys.platform == "win32":
            claude_path = shutil.which("claude.cmd")

        if claude_path:
            console.print(f"  [green]{SYM_OK}[/green] Claude CLI found: {claude_path}")
        else:
            errors.append("Claude CLI not found in PATH")

        # 3. Check backlog file exists and is valid
        backlog_path = self.project_path / self.config.backlog_file
        if not backlog_path.exists():
            errors.append(f"Backlog file not found: {backlog_path}")
        else:
            try:
                data = json.loads(backlog_path.read_text())
                Backlog.model_validate(data)
                console.print(f"  [green]{SYM_OK}[/green] Backlog file valid: {backlog_path.name}")
            except json.JSONDecodeError as e:
                errors.append(f"Backlog file is not valid JSON: {e}")
            except Exception as e:
                errors.append(f"Backlog file validation failed: {e}")

        # 4. Check disk space (>100MB free)
        try:
            if sys.platform == "win32":
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    str(self.project_path),
                    None,
                    None,
                    ctypes.pointer(free_bytes)
                )
                free_mb = free_bytes.value / (1024 * 1024)
            else:
                import os
                stat = os.statvfs(self.project_path)
                free_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)

            if free_mb < 100:
                errors.append(f"Low disk space: {free_mb:.0f}MB free (need >100MB)")
            else:
                console.print(f"  [green]{SYM_OK}[/green] Disk space: {free_mb:.0f}MB free")
        except Exception as e:
            warnings.append(f"Could not check disk space: {e}")

        # 5. Check required tools
        for tool in ["git", "python"]:
            if shutil.which(tool):
                console.print(f"  [green]{SYM_OK}[/green] {tool} found")
            else:
                errors.append(f"Required tool not found: {tool}")

        # 6. Check ANTHROPIC_API_KEY if using SDK mode
        if self.config.session_mode.value == "sdk":
            import os
            if os.environ.get("ANTHROPIC_API_KEY"):
                console.print(f"  [green]{SYM_OK}[/green] ANTHROPIC_API_KEY set")
            else:
                warnings.append("ANTHROPIC_API_KEY not set (required for SDK mode)")

        # Print warnings
        for warning in warnings:
            console.print(f"  [yellow]{SYM_WARN}[/yellow] {warning}")

        return errors, warnings

    def load_backlog(self) -> Backlog:
        """Load the feature backlog from JSON file."""
        backlog_path = self.project_path / self.config.backlog_file

        if not backlog_path.exists():
            raise FileNotFoundError(
                f"Backlog file not found: {backlog_path}\n"
                f"Create a {self.config.backlog_file} with your features."
            )

        data = json.loads(backlog_path.read_text())
        self.backlog = Backlog.model_validate(data)
        return self.backlog

    def save_backlog(self) -> None:
        """Save the backlog back to JSON file."""
        if not self.backlog:
            return

        backlog_path = self.project_path / self.config.backlog_file
        backlog_path.write_text(self.backlog.model_dump_json(indent=2))

    async def run(self) -> None:
        """Main entry point - run until backlog is complete."""
        # Set up signal handlers for graceful shutdown
        self._recovery_manager.setup_signal_handlers()

        console.print(Panel(
            f"[bold]Autonomous Development Agent[/bold]\n"
            f"Project: {self.project_path.name}",
            title="ADA Harness"
        ))

        # Run health checks
        errors, warnings = await self._run_health_checks()

        if errors:
            console.print("\n[red]Health check failed:[/red]")
            for error in errors:
                console.print(f"  [red]{SYM_FAIL}[/red] {error}")
            console.print("\n[red]Cannot proceed. Fix the issues above and try again.[/red]")
            return

        if warnings:
            console.print(f"\n[yellow]{len(warnings)} warning(s) - proceeding anyway[/yellow]")

        # Load backlog
        try:
            self.load_backlog()
        except FileNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            return

        console.print(f"\nLoaded {len(self.backlog.features)} features")

        # Check for recovery from interrupted session
        recovery_feature_id = await self._recovery_manager.check_for_recovery()

        # Check if initialization needed
        progress_exists = (self.project_path / self.config.progress_file).exists()
        if not progress_exists:
            result = await self._orchestrator.run_initializer(self.backlog)
            if not result.success:
                console.print("[red]Initialization failed. Stopping.[/red]")
                return
            self.total_sessions += 1
            self.initialized = True

        # Main loop
        while not self.backlog.is_complete() and self.sessions.should_continue():
            # Check for shutdown request
            if self._recovery_manager.is_shutdown_requested():
                await self._recovery_manager.graceful_shutdown()
                return

            feature = self.backlog.get_next_feature()

            if not feature:
                console.print("[yellow]No eligible features to work on (check dependencies)[/yellow]")
                break

            # Track current feature for shutdown handling
            self._recovery_manager.set_current_context(
                feature=feature,
                session=self.sessions.current_session
            )

            console.print(f"\n{'='*60}")
            console.print(f"Session {self.total_sessions + 1}")
            console.print(f"{'='*60}")

            result = await self._orchestrator.run_coding_session_with_retry(
                feature, self.backlog
            )
            self.total_sessions += 1

            # Save backlog after each session
            self.save_backlog()

            # Check for shutdown after session
            if self._recovery_manager.is_shutdown_requested():
                await self._recovery_manager.graceful_shutdown()
                return

            if not result.success and not result.handoff_requested:
                # Check if it's a non-retryable error
                if result.error_category in (ErrorCategory.BILLING, ErrorCategory.AUTH):
                    console.print(f"[red]Fatal error ({result.error_category.value}): {result.error_message}[/red]")
                    console.print("[red]Stopping due to non-recoverable error.[/red]")
                    break
                else:
                    console.print(f"[red]Session failed after retries: {result.error_message}[/red]")
                    # Continue to next feature
                    continue

            # Brief pause between sessions
            await asyncio.sleep(2)

        # Summary
        completed = sum(1 for f in self.backlog.features if f.status == FeatureStatus.COMPLETED)
        cost_summary = self.session_history.get_cost_summary()
        console.print(Panel(
            f"[bold]Sessions run:[/bold] {self.total_sessions}\n"
            f"[bold]Features completed:[/bold] {completed}/{len(self.backlog.features)}\n"
            f"[bold]Total cost:[/bold] ${cost_summary.total_cost_usd:.4f}\n"
            f"[bold]Total tokens:[/bold] {CostTracker.format_tokens(cost_summary.total_input_tokens)} in / "
            f"{CostTracker.format_tokens(cost_summary.total_output_tokens)} out",
            title="Summary"
        ))


async def run_harness(
    project_path: str,
    config: Optional[HarnessConfig] = None
) -> None:
    """Convenience function to run the harness."""
    harness = AutonomousHarness(project_path, config)
    await harness.run()
