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
from typing import Optional, List, Tuple, TypedDict

from rich.console import Console
from rich.panel import Panel

from .models import (
    Backlog, Feature, FeatureStatus, HarnessConfig,
    ProgressEntry, ErrorCategory, CheckpointState, VerificationConfig,
    HealthIssueSeverity,
)
from .progress import ProgressTracker
from .git_manager import GitManager
from .session import SessionManager, BaseSession, SessionResult
from .token_tracker import TokenTracker, format_tokens
from .session_history import SessionHistory
from .model_selector import ModelSelector
from .alert_manager import AlertManager
from .workspace import WorkspaceManager
from .verification import FeatureVerifier
from .workspace_health import WorkspaceHealthChecker, WorkspaceCleaner

# Import orchestration components
from .orchestration import (
    SessionOrchestrator,
    FeatureCompletionHandler,
    SessionRecoveryManager,
)

# Import protocols for type hints
from .protocols import GitOperations, ProgressLog


class ProjectTypeInfo(TypedDict):
    """Result of project type detection."""
    framework: Optional[str]  # 'node', 'python', or None
    has_ui: bool
    test_command: Optional[str]


def detect_project_type(project_path: Path) -> ProjectTypeInfo:
    """Detect project type and appropriate testing configuration.

    Analyzes the project structure to determine:
    - Framework (Node.js, Python, or unknown)
    - Whether the project has a user-facing UI
    - Appropriate test command based on detection

    Args:
        project_path: Path to the project directory

    Returns:
        ProjectTypeInfo with framework, has_ui, and test_command
    """
    has_ui = False
    framework: Optional[str] = None

    # Check for Node.js project
    pkg_json = project_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            # Check for UI frameworks
            ui_frameworks = ["react", "vue", "svelte", "angular", "next", "nuxt", "@sveltejs/kit"]
            has_ui = any(d in deps for d in ui_frameworks)

            framework = "node"

            # Determine test command based on scripts and UI detection
            scripts = pkg.get("scripts", {})
            if has_ui:
                # Check if E2E and unit tests are configured
                has_e2e = "test:e2e" in scripts or "playwright" in deps
                has_unit = "test" in scripts or "vitest" in deps or "jest" in deps
                if has_e2e and has_unit:
                    test_command = "npm run test && npm run test:e2e"
                elif has_unit:
                    test_command = "npm run test"
                else:
                    test_command = "npm test"  # Default
            else:
                # Non-UI Node.js project
                test_command = "npm run test" if "test" in scripts else "npm test"

            return ProjectTypeInfo(
                framework=framework,
                has_ui=has_ui,
                test_command=test_command
            )
        except (json.JSONDecodeError, IOError):
            pass

    # Check for Python project
    pyproject = project_path / "pyproject.toml"
    setup_py = project_path / "setup.py"
    requirements = project_path / "requirements.txt"

    if pyproject.exists() or setup_py.exists() or requirements.exists():
        framework = "python"

        # Check for UI indicators in Python projects
        templates_dir = project_path / "templates"
        static_dir = project_path / "static"
        has_ui = templates_dir.exists() or static_dir.exists()

        # Check for Flask/Django/FastAPI in dependencies
        try:
            if pyproject.exists():
                content = pyproject.read_text()
                web_frameworks = ["flask", "django", "fastapi", "streamlit", "gradio"]
                if any(fw in content.lower() for fw in web_frameworks):
                    has_ui = True
        except IOError:
            pass

        # Determine test command
        if has_ui:
            test_command = "pytest && playwright test"
        else:
            test_command = "pytest"

        return ProjectTypeInfo(
            framework=framework,
            has_ui=has_ui,
            test_command=test_command
        )

    # Unknown project type
    return ProjectTypeInfo(
        framework=None,
        has_ui=False,
        test_command=None
    )


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

        # Auto-detect project type and test command if not configured
        self._auto_configure_testing()

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
        self.token_tracker = TokenTracker(self.config.model)
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
            stop_check=self._recovery_manager.is_shutdown_requested,
        )

        # Wire up circular dependencies between orchestration components
        self._orchestrator.set_completion_handler(self._completion_handler)
        self._orchestrator.set_recovery_manager(self._recovery_manager)

        # State
        self.backlog: Optional[Backlog] = None
        self.initialized = False
        self.total_sessions = 0

        # Checkpoint state for periodic build verification
        self._checkpoint_state = CheckpointState()

    def _auto_configure_testing(self) -> None:
        """Auto-detect project type and configure testing if not already set.

        Sets test_command, has_ui, and project_framework based on project analysis.
        Does not override explicitly set values.
        """
        # Skip if test_command is already configured
        if self.config.test_command is not None:
            return

        # Detect project type
        project_info = detect_project_type(self.project_path)

        # Set config values if not already set
        if self.config.has_ui is None:
            self.config.has_ui = project_info["has_ui"]

        if self.config.project_framework is None:
            self.config.project_framework = project_info["framework"]

        if self.config.test_command is None and project_info["test_command"]:
            self.config.test_command = project_info["test_command"]

        # Log detection results
        if project_info["framework"]:
            ui_status = "with UI" if project_info["has_ui"] else "no UI"
            console.print(
                f"[dim]Auto-detected: {project_info['framework']} project ({ui_status}), "
                f"test command: {project_info['test_command']}[/dim]"
            )

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

        # 2. Check ANTHROPIC_API_KEY (optional - SDK can use Claude Code subscription auth)
        import os
        if os.environ.get("ANTHROPIC_API_KEY"):
            console.print(f"  [green]{SYM_OK}[/green] ANTHROPIC_API_KEY is set")
        else:
            # Not an error - SDK can authenticate via Claude Code subscription
            console.print(f"  [yellow]{SYM_WARN}[/yellow] ANTHROPIC_API_KEY not set (using subscription auth)")

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

        # 6. Double-check ANTHROPIC_API_KEY is set
        # (Already checked earlier, but verify again for completeness)
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            # Only warn here since we errored earlier
            pass

        # Print warnings
        for warning in warnings:
            console.print(f"  [yellow]{SYM_WARN}[/yellow] {warning}")

        return errors, warnings

    async def _run_workspace_health_check(self) -> bool:
        """Run workspace health checks and auto-fix safe issues.

        Returns:
            True if workspace is healthy (or was repaired), False if critical issues remain
        """
        console.print("\n[blue]Running workspace health check...[/blue]")

        checker = WorkspaceHealthChecker(
            self.project_path,
            workspace=self.workspace,
            git=self.git,
            backlog_file=self.config.backlog_file
        )
        report = checker.check_all()

        if report.healthy:
            console.print(f"  [green]{SYM_OK}[/green] Workspace is healthy")
            return True

        # Show found issues
        for issue in report.issues:
            if issue.severity == HealthIssueSeverity.CRITICAL:
                console.print(f"  [red]{SYM_FAIL}[/red] {issue.message}")
            elif issue.severity == HealthIssueSeverity.WARNING:
                console.print(f"  [yellow]{SYM_WARN}[/yellow] {issue.message}")
            else:
                console.print(f"  [dim][-][/dim] {issue.message}")

        # Auto-fix safe issues
        cleaner = WorkspaceCleaner(self.project_path, workspace=self.workspace)
        fixed = cleaner.fix_auto(report)

        if fixed:
            console.print(f"  [green]{SYM_OK}[/green] Auto-fixed {len(fixed)} issue(s)")

        # Block on critical issues
        if report.critical_count > 0:
            console.print(f"\n[red]{SYM_FAIL} Critical workspace issues detected.[/red]")
            console.print("[red]Run 'ada health --fix-all' to attempt repair.[/red]")
            return False

        if report.warning_count > 0:
            console.print(f"  [yellow]{SYM_WARN}[/yellow] {report.warning_count} warning(s) remain (proceeding anyway)")

        return True

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

        # Run workspace health check
        if self.workspace.exists():
            if not await self._run_workspace_health_check():
                return

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

            # Check for periodic checkpoint after feature completion
            if result.feature_completed and self.config.checkpoint_interval > 0:
                self._checkpoint_state.features_since_last_checkpoint += 1

                if self._checkpoint_state.features_since_last_checkpoint >= self.config.checkpoint_interval:
                    checkpoint_passed = await self._run_checkpoint()
                    if not checkpoint_passed:
                        console.print("[red]Checkpoint failed after max fix attempts. Stopping.[/red]")
                        break

            # Check for shutdown after session (or if session was interrupted)
            if result.interrupted or self._recovery_manager.is_shutdown_requested():
                # Session was interrupted mid-execution or stop requested after
                # The orchestrator already handled committing work, just exit cleanly
                console.print("[yellow]Graceful shutdown complete.[/yellow]")
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
        token_summary = self.session_history.get_token_summary()
        console.print(Panel(
            f"[bold]Sessions run:[/bold] {self.total_sessions}\n"
            f"[bold]Features completed:[/bold] {completed}/{len(self.backlog.features)}\n"
            f"[bold]Total tokens:[/bold] {format_tokens(token_summary.total_input_tokens)} in / "
            f"{format_tokens(token_summary.total_output_tokens)} out",
            title="Summary"
        ))


    async def _run_checkpoint(self) -> bool:
        """Run periodic integration checkpoint with auto-fix.

        Returns:
            True if checkpoint passed, False if failed after max attempts
        """
        from datetime import datetime

        console.print("\n" + "=" * 60)
        console.print("[bold yellow]Running Integration Checkpoint[/bold yellow]")
        console.print("=" * 60)

        # Get verification config, use defaults if not configured
        verification_config = self.config.verification or VerificationConfig()
        verifier = FeatureVerifier(self.project_path, verification_config)

        # Run the checkpoint
        report = verifier.run_full_checkpoint()

        if report.passed:
            console.print(f"\n[green]{SYM_OK} Checkpoint passed![/green]")
            self._checkpoint_state.features_since_last_checkpoint = 0
            self._checkpoint_state.last_checkpoint_at = datetime.now()
            self._checkpoint_state.last_checkpoint_passed = True
            self._checkpoint_state.current_fix_attempt = 0
            return True

        # Checkpoint failed - show results
        console.print(f"\n[red]{SYM_FAIL} Checkpoint failed![/red]")
        for result in report.results:
            if result.skipped:
                console.print(f"  [dim][-] {result.name}: {result.message}[/dim]")
            elif result.passed:
                console.print(f"  [green]{SYM_OK} {result.name}[/green]: {result.message}")
            else:
                console.print(f"  [red]{SYM_FAIL} {result.name}[/red]: {result.message}")
                if result.details:
                    # Truncate long details
                    details = result.details[:500] + "..." if len(result.details) > 500 else result.details
                    console.print(f"    [dim]{details}[/dim]")

        # Attempt auto-fix
        for attempt in range(1, self.config.checkpoint_max_fix_attempts + 1):
            self._checkpoint_state.current_fix_attempt = attempt
            console.print(f"\n[yellow]Auto-fix attempt {attempt}/{self.config.checkpoint_max_fix_attempts}...[/yellow]")

            fix_result = await self._run_fix_session(report)

            # Re-run checkpoint after fix attempt
            report = verifier.run_full_checkpoint()

            if report.passed:
                console.print(f"\n[green]{SYM_OK} Checkpoint passed after fix attempt {attempt}![/green]")
                self._checkpoint_state.features_since_last_checkpoint = 0
                self._checkpoint_state.last_checkpoint_at = datetime.now()
                self._checkpoint_state.last_checkpoint_passed = True
                self._checkpoint_state.current_fix_attempt = 0
                return True

            console.print(f"[red]{SYM_FAIL} Checkpoint still failing after fix attempt {attempt}[/red]")

        # All fix attempts exhausted
        self._checkpoint_state.last_checkpoint_passed = False
        return False

    async def _run_fix_session(self, failed_report) -> SessionResult:
        """Run auto-fix session to repair checkpoint failures.

        Args:
            failed_report: The VerificationReport with failed checks

        Returns:
            SessionResult from the fix session
        """
        # Format error description
        error_lines = []
        for result in failed_report.results:
            if not result.passed and not result.skipped:
                error_lines.append(f"## {result.name}")
                error_lines.append(f"**Status**: FAILED")
                error_lines.append(f"**Message**: {result.message}")
                if result.details:
                    error_lines.append(f"**Details**:\n```\n{result.details}\n```")
                error_lines.append("")

        error_description = "\n".join(error_lines)

        # Load the checkpoint fix prompt template
        try:
            fix_prompt = self._orchestrator._load_prompt_template("checkpoint_fix")
        except FileNotFoundError:
            # Fallback to inline prompt if template not found
            fix_prompt = """You are an autonomous development agent performing an emergency fix session.

## Context
- Working Directory: {project_path}
- Fix Attempt: {fix_attempt}

## Problem
An integration checkpoint has failed. Fix the errors below.

{error_description}

## Instructions

1. **Analyze** - Read errors carefully. Fix the FIRST error (later ones often cascade)
2. **Fix** - Make minimal, focused changes
3. **Verify** - Re-run the failing command after each fix
4. **Commit** - `fix: resolve checkpoint failures`

## Constraints
- Do NOT introduce new features
- Do NOT delete tests to make them pass
- Focus ONLY on fixing the failing checks
"""

        prompt = fix_prompt.format(
            project_path=str(self.project_path),
            error_description=error_description,
            fix_attempt=self._checkpoint_state.current_fix_attempt
        )

        # Create a session for the fix
        session = self.sessions.create_session()

        # Run the fix session
        console.print("[dim]Running fix session...[/dim]")
        result = await session.run(prompt)

        # Log the fix attempt
        self.progress.append_entry(ProgressEntry(
            session_id=session.session_id,
            action="checkpoint_fix",
            summary=f"Auto-fix attempt {self._checkpoint_state.current_fix_attempt} for checkpoint failures"
        ))

        return result


async def run_harness(
    project_path: str,
    config: Optional[HarnessConfig] = None
) -> None:
    """Convenience function to run the harness."""
    harness = AutonomousHarness(project_path, config)
    await harness.run()
