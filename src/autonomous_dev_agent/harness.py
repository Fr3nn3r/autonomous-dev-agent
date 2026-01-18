"""Main harness orchestrator for autonomous development.

This is the core engine that:
1. Loads the backlog
2. Runs initialization (first time only)
3. Loops through sessions until backlog is complete
4. Handles handoffs between sessions
"""

import asyncio
import json
import random
import shutil
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any, Tuple, List

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import (
    Backlog, Feature, FeatureStatus, HarnessConfig,
    SessionState, ProgressEntry, ErrorCategory, RetryConfig,
    SessionOutcome, SessionRecord, VerificationConfig
)
from .progress import ProgressTracker
from .git_manager import GitManager
from .session import SessionManager, AgentSession, SessionResult
from .validators import QualityGateValidator
from .verification import FeatureVerifier
from .cost_tracker import CostTracker
from .session_history import SessionHistory, create_session_record
from .model_selector import ModelSelector
from .alert_manager import (
    AlertManager,
    create_session_failed_alert,
    create_feature_completed_alert,
    create_handoff_alert,
    create_cost_threshold_alert,
)


console = Console()


class AutonomousHarness:
    """Main orchestrator for long-running autonomous development.

    Based on Anthropic's two-agent pattern:
    - Initializer agent sets up environment once
    - Coding agent makes incremental progress per session
    - Clean handoffs enable arbitrary-length development
    """

    def __init__(
        self,
        project_path: str | Path,
        config: Optional[HarnessConfig] = None
    ):
        self.project_path = Path(project_path).resolve()
        self.config = config or HarnessConfig()

        # Core components
        self.backlog: Optional[Backlog] = None
        self.progress = ProgressTracker(
            self.project_path,
            self.config.progress_file,
            rotation_threshold_kb=self.config.progress_rotation_threshold_kb,
            keep_entries=self.config.progress_keep_entries
        )
        self.git = GitManager(self.project_path)
        self.sessions = SessionManager(self.config, self.project_path)
        self.session_history = SessionHistory(self.project_path)
        self.cost_tracker = CostTracker(self.config.model)
        self.model_selector = ModelSelector(default_model=self.config.model)
        self.alert_manager = AlertManager(self.project_path, enable_desktop_notifications=True)

        # State
        self.initialized = False
        self.total_sessions = 0
        self._shutdown_requested = False
        self._current_feature: Optional[Feature] = None
        self._total_cost_usd = 0.0
        self._cost_threshold_alerted = False  # Track if we've already alerted for cost threshold

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        # Note: On Windows, only SIGINT (Ctrl+C) is supported
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)

        # SIGTERM is not available on Windows
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._handle_shutdown_signal)

    def _handle_shutdown_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal by setting flag."""
        signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        console.print(f"\n[yellow]Shutdown signal received ({signal_name}) - finishing current work...[/yellow]")
        self._shutdown_requested = True

    async def _graceful_shutdown(self) -> None:
        """Perform graceful shutdown - commit current work, save state, exit cleanly."""
        console.print("\n[yellow]Performing graceful shutdown...[/yellow]")

        # Commit any uncommitted changes
        git_status = self.git.get_status()
        commit_hash = None

        if git_status.has_changes:
            console.print("[yellow]Committing uncommitted changes...[/yellow]")
            self.git.stage_all()
            commit_hash = self.git.commit(
                "wip: interrupted by shutdown signal\n\n"
                "Auto-committed by autonomous-dev-agent during shutdown.\n"
                f"Feature in progress: {self._current_feature.name if self._current_feature else 'unknown'}"
            )
            if commit_hash:
                console.print(f"[green]Committed:[/green] {commit_hash[:8]}")

        # Log the shutdown
        self.progress.append_entry(ProgressEntry(
            session_id=self.sessions.current_session.session_id if self.sessions.current_session else "shutdown",
            feature_id=self._current_feature.id if self._current_feature else None,
            action="shutdown",
            summary="Graceful shutdown initiated by user signal",
            commit_hash=commit_hash
        ))

        # Save session state for recovery
        if self.sessions.current_session and self._current_feature:
            self._save_session_state(
                self.sessions.current_session,
                self._current_feature,
                handoff_notes="Session interrupted by shutdown signal"
            )
            console.print("[green]Session state saved for recovery[/green]")

        console.print("[green]Shutdown complete.[/green]")

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
            console.print("  [green]✓[/green] Git repository found")

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
            console.print(f"  [green]✓[/green] Claude CLI found: {claude_path}")
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
                console.print(f"  [green]✓[/green] Backlog file valid: {backlog_path.name}")
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
                console.print(f"  [green]✓[/green] Disk space: {free_mb:.0f}MB free")
        except Exception as e:
            warnings.append(f"Could not check disk space: {e}")

        # 5. Check required tools
        for tool in ["git", "python"]:
            if shutil.which(tool):
                console.print(f"  [green]✓[/green] {tool} found")
            else:
                errors.append(f"Required tool not found: {tool}")

        # 6. Check ANTHROPIC_API_KEY if using SDK mode
        if self.config.session_mode.value == "sdk":
            import os
            if os.environ.get("ANTHROPIC_API_KEY"):
                console.print("  [green]✓[/green] ANTHROPIC_API_KEY set")
            else:
                warnings.append("ANTHROPIC_API_KEY not set (required for SDK mode)")

        # Print warnings
        for warning in warnings:
            console.print(f"  [yellow]![/yellow] {warning}")

        return errors, warnings

    def _calculate_retry_delay(self, attempt: int, retry_config: RetryConfig) -> float:
        """Calculate delay for exponential backoff with jitter.

        Args:
            attempt: Current retry attempt (0-indexed)
            retry_config: Retry configuration

        Returns:
            Delay in seconds
        """
        # Exponential backoff: base_delay * (exponential_base ^ attempt)
        delay = retry_config.base_delay_seconds * (
            retry_config.exponential_base ** attempt
        )

        # Cap at max delay
        delay = min(delay, retry_config.max_delay_seconds)

        # Add jitter (+/- jitter_factor)
        jitter = delay * retry_config.jitter_factor
        delay += random.uniform(-jitter, jitter)

        return max(0, delay)  # Never negative

    async def _run_tests(self) -> Tuple[bool, str]:
        """Run the configured test command.

        Returns:
            Tuple of (success, output_message)
        """
        if not self.config.test_command:
            return True, "No test command configured"

        console.print(f"\n[blue]Running tests:[/blue] {self.config.test_command}")

        try:
            # Run the test command
            result = subprocess.run(
                self.config.test_command,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for tests
            )

            if result.returncode == 0:
                console.print("[green]Tests passed![/green]")
                return True, "Tests passed"
            else:
                console.print(f"[red]Tests failed (exit code {result.returncode})[/red]")
                output = result.stdout + result.stderr
                # Truncate output for display
                if len(output) > 1000:
                    output = output[:1000] + "\n... (truncated)"
                console.print(f"[dim]{output}[/dim]")
                return False, f"Tests failed (exit {result.returncode}): {output[:500]}"

        except subprocess.TimeoutExpired:
            console.print("[red]Tests timed out after 5 minutes[/red]")
            return False, "Tests timed out after 5 minutes"
        except Exception as e:
            console.print(f"[red]Error running tests: {e}[/red]")
            return False, f"Error running tests: {e}"

    def _should_retry(
        self,
        result: SessionResult,
        attempt: int,
        retry_config: RetryConfig
    ) -> bool:
        """Determine if we should retry based on error category.

        Args:
            result: The session result with error info
            attempt: Current retry attempt (0-indexed)
            retry_config: Retry configuration

        Returns:
            True if we should retry, False otherwise
        """
        # Don't retry if we've exhausted attempts
        if attempt >= retry_config.max_retries:
            return False

        # Don't retry successful sessions or handoffs
        if result.success or result.handoff_requested:
            return False

        # Check if the error category is retryable
        if result.error_category and result.error_category in retry_config.retryable_categories:
            return True

        # For UNKNOWN errors, retry once
        if result.error_category == ErrorCategory.UNKNOWN and attempt == 0:
            return True

        return False

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

    def _load_prompt_template(self, name: str) -> str:
        """Load a prompt template from the prompts directory."""
        # First check project-local prompts
        local_prompts = self.project_path / ".ada" / "prompts" / f"{name}.txt"
        if local_prompts.exists():
            return local_prompts.read_text()

        # Fall back to package prompts
        package_prompts = Path(__file__).parent / "prompts" / f"{name}.txt"
        if package_prompts.exists():
            return package_prompts.read_text()

        raise FileNotFoundError(f"Prompt template not found: {name}")

    def _format_acceptance_criteria(self, feature: Feature) -> str:
        """Format acceptance criteria as a readable list."""
        if not feature.acceptance_criteria:
            return "- No specific criteria defined"
        return "\n".join(f"- [ ] {c}" for c in feature.acceptance_criteria)

    def _format_security_checklist(self, feature: Feature) -> str:
        """Format security checklist from quality gates."""
        # Get merged gates
        gates = self._get_merged_gates(feature)
        if not gates or not gates.security_checklist:
            return "No security checklist defined for this feature."

        lines = ["Before marking this feature complete, verify:"]
        for item in gates.security_checklist:
            lines.append(f"- [ ] {item}")
        return "\n".join(lines)

    def _format_quality_gates_info(self, feature: Feature) -> str:
        """Format quality gates information for the prompt."""
        gates = self._get_merged_gates(feature)
        if not gates:
            return "No quality gates configured for this feature."

        info = []
        if gates.require_tests:
            info.append("- Tests are required before completion")
        if gates.max_file_lines:
            info.append(f"- Files must be under {gates.max_file_lines} lines")
        if gates.lint_command:
            info.append(f"- Lint check will run: `{gates.lint_command}`")
        if gates.type_check_command:
            info.append(f"- Type check will run: `{gates.type_check_command}`")
        if gates.custom_validators:
            info.append(f"- {len(gates.custom_validators)} custom validator(s) configured")

        if not info:
            return "No quality gates configured for this feature."

        return "The following quality gates must pass:\n" + "\n".join(info)

    def _get_merged_gates(self, feature: Feature):
        """Get merged quality gates for a feature."""
        from .validators import QualityGateValidator
        validator = QualityGateValidator(self.project_path)
        return validator._merge_gates(feature.quality_gates, self.config.default_quality_gates)

    def _format_feature_summary(self) -> str:
        """Create a summary of features for the initializer."""
        if not self.backlog:
            return "No features loaded"

        lines = []
        for i, f in enumerate(self.backlog.features, 1):
            status_icon = "x" if f.status == FeatureStatus.COMPLETED else "o"
            lines.append(f"{i}. [{status_icon}] {f.name} ({f.category.value})")
        return "\n".join(lines)

    async def run_initializer(self) -> SessionResult:
        """Run the initialization agent (first session only)."""
        console.print(Panel(
            "[bold blue]Running Initializer Agent[/bold blue]\n"
            "Setting up development environment...",
            title="Initialization"
        ))

        template = self._load_prompt_template("initializer")
        prompt = template.format(
            project_name=self.backlog.project_name,
            project_path=str(self.project_path),
            feature_count=len(self.backlog.features),
            feature_summary=self._format_feature_summary()
        )

        # Initialize progress file
        self.progress.initialize(self.backlog.project_name)

        session = self.sessions.create_session()
        result = await session.run(prompt, on_message=self._on_message)

        if result.success:
            self.progress.append_entry(ProgressEntry(
                session_id=session.session_id,
                action="initialization_complete",
                summary="Project initialized and ready for development"
            ))
            self.initialized = True

        return result

    async def run_coding_session(self, feature: Feature) -> SessionResult:
        """Run a coding session for a specific feature."""
        # Select appropriate model for this feature
        selected_model = self.model_selector.select_model(feature)
        model_explanation = self.model_selector.explain_selection(feature)

        console.print(Panel(
            f"[bold green]Feature:[/bold green] {feature.name}\n"
            f"[dim]{feature.description}[/dim]\n"
            f"[bold blue]Model:[/bold blue] {model_explanation['model_name']} "
            f"(score: {model_explanation['complexity_score']})",
            title="Coding Session"
        ))

        # Update config to use selected model for this session
        original_model = self.config.model
        self.config.model = selected_model

        # Mark feature as in progress
        self.backlog.mark_feature_started(feature.id)
        self.save_backlog()

        # Build the prompt
        template = self._load_prompt_template("coding")
        prompt = template.format(
            session_id=self.sessions.current_session.session_id if self.sessions.current_session else "new",
            project_name=self.backlog.project_name,
            project_path=str(self.project_path),
            progress_context=self.progress.read_recent(100),
            feature_id=feature.id,
            feature_name=feature.name,
            feature_description=feature.description,
            acceptance_criteria=self._format_acceptance_criteria(feature),
            security_checklist=self._format_security_checklist(feature),
            quality_gates_info=self._format_quality_gates_info(feature)
        )

        # Log session start
        session = self.sessions.create_session()
        self.progress.log_session_start(session.session_id, feature)

        # Save session state for recovery
        self._save_session_state(session, feature)

        # Run the agent
        result = await session.run(prompt, on_message=self._on_message)

        # Handle result
        if result.handoff_requested:
            await self._perform_handoff(session, feature, result)
        elif result.feature_completed or result.success:
            completed = await self._complete_feature(session, feature, result)
            if not completed:
                # Tests failed - feature remains in_progress
                result.feature_completed = False
                # Record as failure
                self._record_session(
                    session, feature, result,
                    outcome=SessionOutcome.FAILURE,
                )
        else:
            # Session failed - record to history
            outcome = SessionOutcome.TIMEOUT if "timeout" in (result.error_message or "").lower() else SessionOutcome.FAILURE
            self._record_session(
                session, feature, result,
                outcome=outcome,
            )

        # Restore original model setting
        self.config.model = original_model

        return result

    async def _perform_handoff(
        self,
        session: AgentSession,
        feature: Feature,
        result: SessionResult
    ) -> None:
        """Perform a clean handoff to the next session."""
        console.print("\n[yellow]WARNING: Context threshold reached - performing handoff...[/yellow]")

        # Get git status
        git_status = self.git.get_status()

        # Auto-commit if configured and there are changes
        commit_hash = None
        if self.config.auto_commit and git_status.has_changes:
            self.git.stage_all()
            commit_hash = self.git.commit(
                f"wip: {feature.name} - session {session.session_id} handoff\n\n"
                f"Auto-committed by autonomous-dev-agent at context threshold.\n"
                f"Context usage: {result.context_usage_percent:.1f}%"
            )

        # Log the handoff
        self.progress.log_handoff(
            session_id=session.session_id,
            feature_id=feature.id,
            summary=result.summary or "Session ended at context threshold",
            files_changed=git_status.modified_files + git_status.staged_files,
            commit_hash=commit_hash,
            next_steps=f"Continue implementing {feature.name}"
        )

        # Add note to feature
        self.backlog.add_implementation_note(
            feature.id,
            f"Session {session.session_id}: Handed off at {result.context_usage_percent:.1f}% context"
        )
        self.save_backlog()

        # Update session state with handoff notes for recovery
        self._save_session_state(
            session,
            feature,
            context_percent=result.context_usage_percent,
            handoff_notes=f"Continue implementing {feature.name}"
        )

        console.print(f"[green]OK[/green] Handoff complete. Commit: {commit_hash or 'no changes'}")

        # Create handoff alert
        create_handoff_alert(
            self.alert_manager,
            session_id=session.session_id,
            feature_id=feature.id,
            context_percent=result.context_usage_percent
        )

        # Record session to history
        self._record_session(
            session, feature, result,
            outcome=SessionOutcome.HANDOFF,
            commit_hash=commit_hash,
            files_changed=git_status.modified_files + git_status.staged_files
        )

    async def _complete_feature(
        self,
        session: AgentSession,
        feature: Feature,
        result: SessionResult
    ) -> bool:
        """Validate and mark a feature as completed.

        Runs quality gate validations and tests before marking complete.
        Uses Phase 3 verification system if configured, otherwise falls back
        to legacy quality gates.

        Returns:
            True if feature was completed, False if validation/tests failed
        """
        # Use Phase 3 verification if configured
        if self.config.verification:
            return await self._complete_feature_with_verification(
                session, feature, result
            )

        # Legacy quality gates flow
        validator = QualityGateValidator(self.project_path)
        validation_report = validator.validate(feature, self.config.default_quality_gates)

        # Log validation results
        for r in validation_report.results:
            if r.passed:
                console.print(f"[green]\u2713[/green] {r.name}: {r.message}")
            else:
                console.print(f"[red]\u2717[/red] {r.name}: {r.message}")
                if r.details:
                    console.print(f"[dim]{r.details}[/dim]")

        if not validation_report.passed:
            console.print(f"[yellow]Feature not completed - {validation_report.error_count} quality gate(s) failed[/yellow]")

            # Log the validation failures
            failed_checks = [r.name for r in validation_report.results if not r.passed]
            self.progress.append_entry(ProgressEntry(
                session_id=session.session_id,
                feature_id=feature.id,
                action="quality_gates_failed",
                summary=f"Quality gates failed: {', '.join(failed_checks)}"
            ))

            # Add note to feature
            self.backlog.add_implementation_note(
                feature.id,
                f"Session {session.session_id}: Quality gates failed - {', '.join(failed_checks)}"
            )
            self.save_backlog()

            return False

        # Run tests if configured
        tests_passed, test_message = await self._run_tests()

        if not tests_passed:
            # Tests failed - do not complete the feature
            console.print(f"[yellow]Feature not completed - tests failed[/yellow]")

            # Log the test failure
            self.progress.append_entry(ProgressEntry(
                session_id=session.session_id,
                feature_id=feature.id,
                action="tests_failed",
                summary=f"Tests failed: {test_message}"
            ))

            # Add note to feature
            self.backlog.add_implementation_note(
                feature.id,
                f"Session {session.session_id}: Tests failed - {test_message}"
            )
            self.save_backlog()

            return False

        # Get commit info
        git_status = self.git.get_status()
        commit_hash = git_status.last_commit_hash

        # Log completion
        self.progress.log_feature_completed(
            session_id=session.session_id,
            feature=feature,
            summary=result.summary or "Feature completed",
            commit_hash=commit_hash
        )

        # Update backlog
        self.backlog.mark_feature_completed(
            feature.id,
            f"Completed in session {session.session_id}"
        )
        self.save_backlog()

        # Clear session state - no longer need recovery
        session.clear_state()

        # Record session to history
        self._record_session(
            session, feature, result,
            outcome=SessionOutcome.SUCCESS,
            commit_hash=commit_hash
        )

        # Create feature completed alert
        create_feature_completed_alert(
            self.alert_manager,
            feature_id=feature.id,
            feature_name=feature.name,
            sessions_spent=feature.sessions_spent
        )

        console.print(f"[green]OK[/green] Feature completed: {feature.name}")
        return True

    async def _complete_feature_with_verification(
        self,
        session: AgentSession,
        feature: Feature,
        result: SessionResult
    ) -> bool:
        """Complete feature using Phase 3 verification system.

        Runs comprehensive verification including:
        - V1: Playwright E2E tests
        - V2: Pre-complete hooks
        - V4: Coverage checking
        - V5: Lint/type checks
        - V6: Manual approval (if required)

        Returns:
            True if feature was completed, False if verification failed
        """
        console.print("\n[bold blue]Running feature verification...[/bold blue]")

        verifier = FeatureVerifier(self.project_path, self.config.verification)
        verification_report = verifier.verify(feature, interactive=True)

        # Log verification results
        for r in verification_report.results:
            if r.skipped:
                console.print(f"[dim]⊘ {r.name}: {r.message}[/dim]")
            elif r.passed:
                duration_str = f" ({r.duration_seconds:.1f}s)" if r.duration_seconds else ""
                console.print(f"[green]✓[/green] {r.name}: {r.message}{duration_str}")
            else:
                console.print(f"[red]✗[/red] {r.name}: {r.message}")
                if r.details:
                    # Show truncated details
                    details = r.details[:500] + "..." if len(r.details) > 500 else r.details
                    console.print(f"[dim]{details}[/dim]")

        # Show coverage if available
        if verification_report.coverage:
            cov = verification_report.coverage
            console.print(f"\n[bold]Coverage:[/bold] {cov.coverage_percent:.1f}% "
                         f"({cov.covered_lines}/{cov.total_lines} lines)")

        # Check if verification passed
        if not verification_report.passed:
            failed_checks = [r.name for r in verification_report.results if not r.passed and not r.skipped]
            console.print(f"\n[yellow]Feature not completed - verification failed[/yellow]")

            # Log the verification failures
            self.progress.append_entry(ProgressEntry(
                session_id=session.session_id,
                feature_id=feature.id,
                action="verification_failed",
                summary=f"Verification failed: {', '.join(failed_checks)}"
            ))

            # Add note to feature
            self.backlog.add_implementation_note(
                feature.id,
                f"Session {session.session_id}: Verification failed - {', '.join(failed_checks)}"
            )
            self.save_backlog()

            return False

        # Check manual approval status
        if verification_report.requires_approval and not verification_report.approved:
            console.print(f"\n[yellow]Feature not completed - manual approval required but not given[/yellow]")

            self.progress.append_entry(ProgressEntry(
                session_id=session.session_id,
                feature_id=feature.id,
                action="approval_required",
                summary="Manual approval required but not given"
            ))

            return False

        # Get commit info
        git_status = self.git.get_status()
        commit_hash = git_status.last_commit_hash

        # Log completion
        approval_note = ""
        if verification_report.requires_approval:
            approval_note = f" (approved by {verification_report.approved_by})"

        self.progress.log_feature_completed(
            session_id=session.session_id,
            feature=feature,
            summary=f"{result.summary or 'Feature completed'}{approval_note}",
            commit_hash=commit_hash
        )

        # Update backlog
        self.backlog.mark_feature_completed(
            feature.id,
            f"Completed in session {session.session_id}{approval_note}"
        )
        self.save_backlog()

        # Clear session state - no longer need recovery
        session.clear_state()

        # Record session to history
        self._record_session(
            session, feature, result,
            outcome=SessionOutcome.SUCCESS,
            commit_hash=commit_hash
        )

        # Create feature completed alert
        create_feature_completed_alert(
            self.alert_manager,
            feature_id=feature.id,
            feature_name=feature.name,
            sessions_spent=feature.sessions_spent
        )

        console.print(f"\n[green]✓[/green] Feature completed: {feature.name}")
        return True

    async def _run_coding_session_with_retry(self, feature: Feature) -> SessionResult:
        """Run a coding session with automatic retry on transient errors.

        Args:
            feature: The feature to work on

        Returns:
            SessionResult from the final attempt
        """
        retry_config = self.config.retry
        last_result: Optional[SessionResult] = None

        for attempt in range(retry_config.max_retries + 1):
            if attempt > 0:
                # Log retry attempt
                delay = self._calculate_retry_delay(attempt - 1, retry_config)
                category = last_result.error_category.value if last_result and last_result.error_category else "unknown"

                console.print(f"\n[yellow]Retry {attempt}/{retry_config.max_retries}[/yellow] "
                             f"- Error: {category} - Waiting {delay:.1f}s...")

                # Log to progress file
                self.progress.append_entry(ProgressEntry(
                    session_id=f"retry_{attempt}",
                    feature_id=feature.id,
                    action="retry_attempt",
                    summary=f"Retry attempt {attempt} after {category} error, waiting {delay:.1f}s"
                ))

                await asyncio.sleep(delay)

            # Run the session
            result = await self.run_coding_session(feature)
            last_result = result

            # Check if we should retry
            if not self._should_retry(result, attempt, retry_config):
                return result

            # Log the failure before retrying
            console.print(f"[yellow]Session failed ({result.error_category.value if result.error_category else 'unknown'}): "
                         f"{result.error_message}[/yellow]")

        # Should not reach here, but return last result if we do
        return last_result or SessionResult(
            session_id="retry_exhausted",
            success=False,
            context_usage_percent=0.0,
            error_message="Retry attempts exhausted",
            error_category=ErrorCategory.UNKNOWN
        )

    def _on_message(self, message: Any) -> None:
        """Handle streaming messages from the agent."""
        # For now, just print text messages
        if hasattr(message, 'text'):
            console.print(message.text, end="")

    async def _check_for_recovery(self) -> Optional[str]:
        """Check for interrupted session and prompt for recovery.

        Returns:
            Feature ID to resume, or None to start fresh
        """
        recovery_state = self.sessions.get_recovery_state()

        if not recovery_state:
            return None

        if not recovery_state.current_feature_id:
            # Clear stale state with no feature
            self.sessions.current_session = self.sessions.create_session()
            self.sessions.current_session.clear_state()
            return None

        # Found interrupted session
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

    def _save_session_state(
        self,
        session: AgentSession,
        feature: Feature,
        context_percent: float = 0.0,
        handoff_notes: Optional[str] = None
    ) -> None:
        """Save session state for recovery."""
        state = SessionState(
            session_id=session.session_id,
            current_feature_id=feature.id,
            context_usage_percent=context_percent,
            last_commit_hash=self.git.get_status().last_commit_hash,
            handoff_notes=handoff_notes
        )
        session.save_state(state)

    def _record_session(
        self,
        session: AgentSession,
        feature: Optional[Feature],
        result: SessionResult,
        outcome: SessionOutcome,
        commit_hash: Optional[str] = None,
        files_changed: Optional[list[str]] = None
    ) -> None:
        """Record a completed session to history.

        Args:
            session: The completed session
            feature: Feature being worked on (if any)
            result: Session result
            outcome: How the session ended
            commit_hash: Commit hash if committed
            files_changed: Files modified during the session
        """
        # Create session record
        record = create_session_record(
            session_id=session.session_id,
            feature_id=feature.id if feature else None,
            model=result.model or self.config.model,
            outcome=outcome,
            input_tokens=result.usage_stats.input_tokens,
            output_tokens=result.usage_stats.output_tokens,
            cache_read_tokens=result.usage_stats.cache_read_tokens,
            cache_write_tokens=result.usage_stats.cache_write_tokens,
            cost_usd=result.usage_stats.cost_usd,
            files_changed=files_changed or result.files_changed,
            commit_hash=commit_hash,
            error_message=result.error_message,
            error_category=result.error_category.value if result.error_category else None,
            started_at=result.started_at,
            ended_at=result.ended_at
        )

        # Add to history
        self.session_history.add_record(record)

        # Track cumulative cost
        self._total_cost_usd += result.usage_stats.cost_usd

        # Create alerts based on outcome
        if outcome == SessionOutcome.FAILURE:
            create_session_failed_alert(
                self.alert_manager,
                session_id=session.session_id,
                feature_id=feature.id if feature else None,
                error_message=result.error_message or "Unknown error"
            )

        # Check cost threshold (alert once when exceeding $10)
        cost_threshold = 10.0  # Could be made configurable
        if self._total_cost_usd >= cost_threshold and not self._cost_threshold_alerted:
            self._cost_threshold_alerted = True
            create_cost_threshold_alert(
                self.alert_manager,
                current_cost=self._total_cost_usd,
                threshold=cost_threshold
            )

        # Display cost info
        if result.usage_stats.cost_usd > 0:
            console.print(
                f"[dim]Session cost: ${result.usage_stats.cost_usd:.4f} "
                f"(Total: ${self._total_cost_usd:.4f})[/dim]"
            )

    async def run(self) -> None:
        """Main entry point - run until backlog is complete."""
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()

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
                console.print(f"  [red]✗[/red] {error}")
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
        recovery_feature_id = await self._check_for_recovery()

        # Check if initialization needed
        progress_exists = (self.project_path / self.config.progress_file).exists()
        if not progress_exists:
            result = await self.run_initializer()
            if not result.success:
                console.print("[red]Initialization failed. Stopping.[/red]")
                return
            self.total_sessions += 1

        # Main loop
        while not self.backlog.is_complete() and self.sessions.should_continue():
            # Check for shutdown request
            if self._shutdown_requested:
                await self._graceful_shutdown()
                return

            feature = self.backlog.get_next_feature()

            if not feature:
                console.print("[yellow]No eligible features to work on (check dependencies)[/yellow]")
                break

            # Track current feature for shutdown handling
            self._current_feature = feature

            console.print(f"\n{'='*60}")
            console.print(f"Session {self.total_sessions + 1}")
            console.print(f"{'='*60}")

            result = await self._run_coding_session_with_retry(feature)
            self.total_sessions += 1

            # Check for shutdown after session
            if self._shutdown_requested:
                await self._graceful_shutdown()
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
