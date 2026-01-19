"""Feature completion and verification handling.

Handles:
- Running quality gate validations
- Running tests before marking features complete
- Phase 3 verification system integration
- Recording session history
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Callable

from rich.console import Console

from ..models import (
    HarnessConfig, Feature, Backlog, ProgressEntry,
    SessionOutcome, QualityGates, ErrorCategory
)
from ..protocols import GitOperations, ProgressLog
from ..validators import QualityGateValidator
from ..session_history import SessionHistory, create_session_record
from ..alert_manager import (
    AlertManager,
    create_session_failed_alert,
    create_feature_completed_alert,
    create_cost_threshold_alert,
)

if TYPE_CHECKING:
    from ..session import BaseSession, SessionResult
    from ..verification import FeatureVerifier

# Windows-compatible symbols
if sys.platform == "win32":
    SYM_OK = "[OK]"
    SYM_FAIL = "[X]"
else:
    SYM_OK = "✓"
    SYM_FAIL = "✗"

console = Console()


class FeatureCompletionHandler:
    """Handles feature completion, verification, and session recording.

    Single Responsibility: Validate completed work and manage
    the transition from in-progress to completed features.

    Dependencies are injected for testability:
    - GitOperations: For getting commit info
    - ProgressLog: For logging completion events
    - AlertManager: For sending completion/failure alerts
    - SessionHistory: For recording session outcomes
    """

    def __init__(
        self,
        config: HarnessConfig,
        project_path: Path,
        progress: ProgressLog,
        git: GitOperations,
        alert_manager: AlertManager,
        session_history: SessionHistory,
        backlog_saver: Optional[Callable[[], None]] = None,
    ):
        """Initialize the completion handler.

        Args:
            config: Harness configuration
            project_path: Path to the project directory
            progress: Progress log for tracking events
            git: Git operations for status/commit info
            alert_manager: Manager for sending alerts
            session_history: History tracking for sessions
            backlog_saver: Optional callback to save backlog changes
        """
        self.config = config
        self.project_path = Path(project_path)
        self.progress = progress
        self.git = git
        self.alert_manager = alert_manager
        self.session_history = session_history
        self._save_backlog = backlog_saver or (lambda: None)

        # Cost tracking state
        self._total_cost_usd = 0.0
        self._cost_threshold_alerted = False

    def set_backlog_saver(self, saver: Callable[[], None]) -> None:
        """Set the callback for saving backlog changes.

        Args:
            saver: Callable that saves the backlog
        """
        self._save_backlog = saver

    async def run_tests(self) -> tuple[bool, str]:
        """Run the configured test command.

        Returns:
            Tuple of (success, output_message)
        """
        if not self.config.test_command:
            return True, "No test command configured"

        console.print(f"\n[blue]Running tests:[/blue] {self.config.test_command}")

        try:
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

    def _get_merged_gates(self, feature: Feature) -> Optional[QualityGates]:
        """Get merged quality gates for a feature.

        Args:
            feature: Feature to get gates for

        Returns:
            Merged quality gates or None
        """
        validator = QualityGateValidator(self.project_path)
        return validator._merge_gates(feature.quality_gates, self.config.default_quality_gates)

    async def complete_feature(
        self,
        session: "BaseSession",
        feature: Feature,
        result: "SessionResult",
        backlog: Backlog,
    ) -> bool:
        """Validate and mark a feature as completed.

        Runs quality gate validations and tests before marking complete.
        Uses Phase 3 verification system if configured, otherwise falls back
        to legacy quality gates.

        Args:
            session: Current session
            feature: Feature to complete
            result: Session result
            backlog: Backlog to update

        Returns:
            True if feature was completed, False if validation/tests failed
        """
        # Use Phase 3 verification if configured
        if self.config.verification:
            return await self._complete_feature_with_verification(
                session, feature, result, backlog
            )

        # Legacy quality gates flow
        validator = QualityGateValidator(self.project_path)
        validation_report = validator.validate(feature, self.config.default_quality_gates)

        # Log validation results
        for r in validation_report.results:
            if r.passed:
                console.print(f"[green]✓[/green] {r.name}: {r.message}")
            else:
                console.print(f"[red]✗[/red] {r.name}: {r.message}")
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
            backlog.add_implementation_note(
                feature.id,
                f"Session {session.session_id}: Quality gates failed - {', '.join(failed_checks)}"
            )
            self._save_backlog()

            return False

        # Run tests if configured
        tests_passed, test_message = await self.run_tests()

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
            backlog.add_implementation_note(
                feature.id,
                f"Session {session.session_id}: Tests failed - {test_message}"
            )
            self._save_backlog()

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
        backlog.mark_feature_completed(
            feature.id,
            f"Completed in session {session.session_id}"
        )
        self._save_backlog()

        # Clear session state - no longer need recovery
        session.clear_state()

        # Record session to history
        self.record_session(
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
        session: "BaseSession",
        feature: Feature,
        result: "SessionResult",
        backlog: Backlog,
    ) -> bool:
        """Complete feature using Phase 3 verification system.

        Runs comprehensive verification including:
        - V1: Playwright E2E tests
        - V2: Pre-complete hooks
        - V4: Coverage checking
        - V5: Lint/type checks
        - V6: Manual approval (if required)

        Args:
            session: Current session
            feature: Feature to complete
            result: Session result
            backlog: Backlog to update

        Returns:
            True if feature was completed, False if verification failed
        """
        from ..verification import FeatureVerifier

        console.print("\n[bold blue]Running feature verification...[/bold blue]")

        verifier = FeatureVerifier(self.project_path, self.config.verification)
        verification_report = verifier.verify(feature, interactive=True)

        # Log verification results
        for r in verification_report.results:
            if r.skipped:
                console.print(f"[dim][-] {r.name}: {r.message}[/dim]")
            elif r.passed:
                duration_str = f" ({r.duration_seconds:.1f}s)" if r.duration_seconds else ""
                console.print(f"[green]{SYM_OK}[/green] {r.name}: {r.message}{duration_str}")
            else:
                console.print(f"[red]{SYM_FAIL}[/red] {r.name}: {r.message}")
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
            backlog.add_implementation_note(
                feature.id,
                f"Session {session.session_id}: Verification failed - {', '.join(failed_checks)}"
            )
            self._save_backlog()

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
        backlog.mark_feature_completed(
            feature.id,
            f"Completed in session {session.session_id}{approval_note}"
        )
        self._save_backlog()

        # Clear session state - no longer need recovery
        session.clear_state()

        # Record session to history
        self.record_session(
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

        console.print(f"\n[green]{SYM_OK}[/green] Feature completed: {feature.name}")
        return True

    def record_session(
        self,
        session: "BaseSession",
        feature: Optional[Feature],
        result: "SessionResult",
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

    def get_total_cost(self) -> float:
        """Get the total cost across all recorded sessions.

        Returns:
            Total cost in USD
        """
        return self._total_cost_usd
