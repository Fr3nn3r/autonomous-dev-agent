"""Session orchestration - managing session lifecycle and execution.

Handles:
- Running initializer and coding sessions
- Prompt template loading and formatting
- Session retry logic with exponential backoff
- Handoff management between sessions
"""

import asyncio
import random
from pathlib import Path
from typing import Optional, Any, Callable, TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel

from ..models import (
    HarnessConfig, Feature, Backlog, ProgressEntry,
    RetryConfig, ErrorCategory, SessionOutcome, QualityGates,
    AssistantMessageEvent, ToolResultEvent
)
from ..protocols import GitOperations, ProgressLog
from ..validators import QualityGateValidator
from ..model_selector import ModelSelector
from ..alert_manager import AlertManager, create_handoff_alert
from ..session_history import SessionHistory
from ..workspace import WorkspaceManager
from ..session_logger import SessionLogger
from ..api.websocket import (
    emit_agent_message, emit_tool_call, emit_tool_result, emit_context_update
)

if TYPE_CHECKING:
    from ..session import SessionManager, BaseSession, SessionResult
    from .feature_completion import FeatureCompletionHandler
    from .recovery import SessionRecoveryManager


console = Console()


class SessionOrchestrator:
    """Orchestrates session execution and lifecycle.

    Single Responsibility: Manage the execution of initializer and coding
    sessions, including prompt generation, retry logic, and handoffs.

    Dependencies are injected for testability:
    - GitOperations: For git status and commits
    - ProgressLog: For session progress tracking
    - SessionManager: For creating and managing sessions
    - WorkspaceManager: For observability workspace
    - ModelSelector: For dynamic model selection
    - AlertManager: For notifications
    - SessionHistory: For recording sessions
    """

    def __init__(
        self,
        config: HarnessConfig,
        project_path: Path,
        progress: ProgressLog,
        git: GitOperations,
        session_manager: "SessionManager",
        workspace: WorkspaceManager,
        model_selector: ModelSelector,
        alert_manager: AlertManager,
        session_history: SessionHistory,
    ):
        """Initialize the session orchestrator.

        Args:
            config: Harness configuration
            project_path: Path to the project directory
            progress: Progress log for tracking events
            git: Git operations
            session_manager: Session manager for creating sessions
            workspace: Workspace manager for observability
            model_selector: Model selector for dynamic selection
            alert_manager: Alert manager for notifications
            session_history: Session history for recording
        """
        self.config = config
        self.project_path = Path(project_path)
        self.progress = progress
        self.git = git
        self.session_manager = session_manager
        self.workspace = workspace
        self.model_selector = model_selector
        self.alert_manager = alert_manager
        self.session_history = session_history

        # Handlers (set via setters for circular dependency handling)
        self._completion_handler: Optional["FeatureCompletionHandler"] = None
        self._recovery_manager: Optional["SessionRecoveryManager"] = None

        # Session logger for current session
        self._current_session_logger: Optional[SessionLogger] = None

        # Live monitoring state
        self._current_session_id: Optional[str] = None
        self._turn_count: int = 0

    def set_completion_handler(self, handler: "FeatureCompletionHandler") -> None:
        """Set the feature completion handler."""
        self._completion_handler = handler

    def set_recovery_manager(self, manager: "SessionRecoveryManager") -> None:
        """Set the recovery manager."""
        self._recovery_manager = manager

    def _load_prompt_template(self, name: str) -> str:
        """Load a prompt template from the prompts directory.

        Args:
            name: Template name (without extension)

        Returns:
            Template content as string

        Raises:
            FileNotFoundError: If template not found
        """
        # First check project-local prompts
        local_prompts = self.project_path / ".ada" / "prompts" / f"{name}.md"
        if local_prompts.exists():
            return local_prompts.read_text()

        # Fall back to package prompts
        package_prompts = Path(__file__).parent.parent / "prompts" / f"{name}.md"
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
        gates = self._get_merged_gates(feature)
        if not gates or not gates.security_checklist:
            return "No security checklist defined for this feature."

        lines = ["Before marking this feature complete, verify:"]
        for item in gates.security_checklist:
            lines.append(f"- [ ] {item}")
        return "\n".join(lines)

    def _format_quality_gates_info(self, feature: Feature) -> str:
        """Format quality gates information for the prompt."""
        info = []

        # Build verification info (from verification config)
        if self.config.verification:
            if self.config.verification.build_command:
                info.append(f"- **BUILD CHECK (MANDATORY)**: `{self.config.verification.build_command}`")
            elif self.config.verification.auto_detect_build:
                info.append("- **BUILD CHECK (MANDATORY)**: Auto-detected from project type")

        gates = self._get_merged_gates(feature)
        if gates:
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

    def _get_merged_gates(self, feature: Feature) -> Optional[QualityGates]:
        """Get merged quality gates for a feature."""
        validator = QualityGateValidator(self.project_path)
        return validator._merge_gates(feature.quality_gates, self.config.default_quality_gates)

    def _format_feature_summary(self, backlog: Backlog) -> str:
        """Create a summary of features for the initializer."""
        from ..models import FeatureStatus

        lines = []
        for i, f in enumerate(backlog.features, 1):
            status_icon = "x" if f.status == FeatureStatus.COMPLETED else "o"
            lines.append(f"{i}. [{status_icon}] {f.name} ({f.category.value})")
        return "\n".join(lines)

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

    def _should_retry(
        self,
        result: "SessionResult",
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

    def _summarize_content(self, content: Optional[str], max_length: int = 100) -> str:
        """Create a brief summary of content for display."""
        if not content:
            return ""
        # Take first line or first max_length chars
        first_line = content.split('\n')[0]
        if len(first_line) > max_length:
            return first_line[:max_length] + "..."
        return first_line

    def _on_message(self, message: Any) -> None:
        """Handle streaming messages from the agent.

        Handles both:
        - Structured events (AssistantMessageEvent, ToolResultEvent) for logging
        - Legacy text messages for display
        """
        # Handle structured events for turn-level logging
        if isinstance(message, AssistantMessageEvent):
            self._turn_count += 1

            if self._current_session_logger:
                self._current_session_logger.log_assistant(
                    content=message.content,
                    tool_calls=message.tool_calls,
                    thinking=message.thinking
                )

            # Emit to WebSocket for live monitoring
            if self._current_session_id:
                tool_call_names = []
                if message.tool_calls:
                    for tc in message.tool_calls:
                        tool_name = tc.get('name', 'unknown') if isinstance(tc, dict) else getattr(tc, 'name', 'unknown')
                        tool_call_names.append(tool_name)

                        # Also emit individual tool.call events
                        call_id = tc.get('id', '') if isinstance(tc, dict) else getattr(tc, 'id', '')
                        params = tc.get('input', {}) if isinstance(tc, dict) else getattr(tc, 'input', {})

                        asyncio.create_task(emit_tool_call(
                            session_id=self._current_session_id,
                            call_id=call_id,
                            tool_name=tool_name,
                            parameters=params if isinstance(params, dict) else {}
                        ))

                asyncio.create_task(emit_agent_message(
                    session_id=self._current_session_id,
                    content=(message.content or "")[:500],
                    summary=self._summarize_content(message.content),
                    tool_calls=tool_call_names,
                    turn=self._turn_count
                ))

        elif isinstance(message, ToolResultEvent):
            if self._current_session_logger:
                self._current_session_logger.log_tool_result(
                    tool_call_id=message.tool_call_id,
                    tool=message.tool,
                    input_data=message.input_data,
                    output=message.output,
                    duration_ms=message.duration_ms,
                    file_changed=message.file_changed
                )

            # Emit to WebSocket for live monitoring
            if self._current_session_id:
                # Determine success based on output content
                output_str = str(message.output) if message.output else ""
                is_error = "error" in output_str.lower() or "exception" in output_str.lower()

                asyncio.create_task(emit_tool_result(
                    session_id=self._current_session_id,
                    call_id=message.tool_call_id or "",
                    tool_name=message.tool or "unknown",
                    success=not is_error,
                    result=output_str[:500] if output_str else "",
                    duration_ms=message.duration_ms
                ))

        # Legacy: print text for display (SDK returns these in addition to events)
        elif hasattr(message, 'text'):
            console.print(message.text, end="")

    async def run_initializer(self, backlog: Backlog) -> "SessionResult":
        """Run the initialization agent (first session only).

        Args:
            backlog: The feature backlog

        Returns:
            SessionResult from the initializer
        """
        console.print(Panel(
            "[bold blue]Running Initializer Agent[/bold blue]\n"
            "Setting up development environment...",
            title="Initialization"
        ))

        # Ensure workspace structure exists
        self.workspace.ensure_structure()

        template = self._load_prompt_template("initializer")
        prompt = template.format(
            project_name=backlog.project_name,
            project_path=str(self.project_path),
            feature_count=len(backlog.features),
            feature_summary=self._format_feature_summary(backlog)
        )

        # Initialize progress file
        self.progress.initialize(backlog.project_name)

        session = self.session_manager.create_session()

        # Create session logger
        session_id = self.workspace.get_next_session_id(
            agent_type="initializer",
            feature_id=None
        )
        self._current_session_logger = SessionLogger(
            workspace=self.workspace,
            session_id=session_id,
            agent_type="initializer",
            model=self.config.model,
            config={
                "context_threshold_percent": self.config.context_threshold_percent,
            }
        )
        self._current_session_logger.log_session_start()
        self._current_session_logger.log_prompt(
            prompt_name="initializer",
            prompt_text=prompt,
            variables={
                "project_name": backlog.project_name,
                "feature_count": len(backlog.features),
            }
        )

        # Set live monitoring state
        self._current_session_id = session.session_id
        self._turn_count = 0

        result = await session.run(prompt, on_message=self._on_message)

        # Log session end
        outcome = "success" if result.success else "failure"
        self._current_session_logger.log_session_end(
            outcome=outcome,
            reason="Initialization complete" if result.success else result.error_message
        )
        self._current_session_logger = None

        # Clear live monitoring state
        self._current_session_id = None
        self._turn_count = 0

        if result.success:
            self.progress.append_entry(ProgressEntry(
                session_id=session.session_id,
                action="initialization_complete",
                summary="Project initialized and ready for development"
            ))

        return result

    async def run_coding_session(
        self,
        feature: Feature,
        backlog: Backlog,
    ) -> "SessionResult":
        """Run a coding session for a specific feature.

        Args:
            feature: Feature to work on
            backlog: The feature backlog

        Returns:
            SessionResult from the coding session
        """
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
        backlog.mark_feature_started(feature.id)

        # Build the prompt
        template = self._load_prompt_template("coding")
        prompt = template.format(
            session_id=self.session_manager.current_session.session_id if self.session_manager.current_session else "new",
            project_name=backlog.project_name,
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
        session = self.session_manager.create_session()
        self.progress.log_session_start(session.session_id, feature)

        # Create session logger for observability
        log_session_id = self.workspace.get_next_session_id(
            agent_type="coding",
            feature_id=feature.id
        )
        self._current_session_logger = SessionLogger(
            workspace=self.workspace,
            session_id=log_session_id,
            agent_type="coding",
            feature_id=feature.id,
            feature_name=feature.name,
            model=selected_model,
            config={
                "context_threshold_percent": self.config.context_threshold_percent,
            }
        )
        self._current_session_logger.log_session_start()
        self._current_session_logger.log_prompt(
            prompt_name="coding",
            prompt_text=prompt,
            variables={
                "feature_id": feature.id,
                "feature_name": feature.name,
                "acceptance_criteria": feature.acceptance_criteria,
            }
        )

        # Save session state for recovery
        if self._recovery_manager:
            self._recovery_manager.save_session_state(session, feature)

        # Set live monitoring state
        self._current_session_id = session.session_id
        self._turn_count = 0

        # Run the agent
        result = await session.run(prompt, on_message=self._on_message)

        # Handle result
        session_outcome = "success"
        session_reason = None
        commit_hash = None

        if result.handoff_requested:
            session_outcome = "handoff"
            session_reason = f"Context threshold reached at {result.context_usage_percent:.1f}%"
            await self._perform_handoff(session, feature, result, backlog)
        elif result.feature_completed or result.success:
            if self._completion_handler:
                completed = await self._completion_handler.complete_feature(
                    session, feature, result, backlog
                )
                if not completed:
                    # Tests failed - feature remains in_progress
                    result.feature_completed = False
                    session_outcome = "failure"
                    session_reason = "Tests or verification failed"
                    # Record as failure
                    self._completion_handler.record_session(
                        session, feature, result,
                        outcome=SessionOutcome.FAILURE,
                    )
                else:
                    session_outcome = "success"
                    session_reason = "Feature completed successfully"
        else:
            # Session failed - record to history
            is_timeout = "timeout" in (result.error_message or "").lower()
            outcome = SessionOutcome.TIMEOUT if is_timeout else SessionOutcome.FAILURE
            session_outcome = "timeout" if is_timeout else "failure"
            session_reason = result.error_message
            if self._completion_handler:
                self._completion_handler.record_session(
                    session, feature, result,
                    outcome=outcome,
                )

        # Log session end to observability workspace
        if self._current_session_logger:
            # Log context/usage update if available
            if result.usage_stats:
                self._current_session_logger.log_context_update(
                    input_tokens=result.usage_stats.input_tokens,
                    output_tokens=result.usage_stats.output_tokens,
                    cache_read_tokens=result.usage_stats.cache_read_tokens,
                    cache_write_tokens=result.usage_stats.cache_write_tokens,
                    cost_usd=result.usage_stats.cost_usd
                )

                # Also emit to WebSocket for live monitoring
                if self._current_session_id:
                    asyncio.create_task(emit_context_update(
                        session_id=self._current_session_id,
                        input_tokens=result.usage_stats.input_tokens,
                        output_tokens=result.usage_stats.output_tokens,
                        total_tokens=result.usage_stats.input_tokens + result.usage_stats.output_tokens,
                        context_percent=result.context_usage_percent,
                        cost_usd=result.usage_stats.cost_usd
                    ))

            # Log any errors
            if result.error_message and result.error_category:
                self._current_session_logger.log_error(
                    category=result.error_category.value,
                    message=result.error_message,
                    recoverable=(session_outcome in ["handoff", "timeout"])
                )

            self._current_session_logger.log_session_end(
                outcome=session_outcome,
                reason=session_reason,
                handoff_notes=f"Continue {feature.name}" if session_outcome == "handoff" else None,
                commit_hash=commit_hash
            )
            self._current_session_logger = None

        # Clear live monitoring state
        self._current_session_id = None
        self._turn_count = 0

        # Restore original model setting
        self.config.model = original_model

        return result

    async def _perform_handoff(
        self,
        session: "BaseSession",
        feature: Feature,
        result: "SessionResult",
        backlog: Backlog,
    ) -> None:
        """Perform a clean handoff to the next session.

        Args:
            session: Current session
            feature: Feature being worked on
            result: Session result
            backlog: The feature backlog
        """
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
        backlog.add_implementation_note(
            feature.id,
            f"Session {session.session_id}: Handed off at {result.context_usage_percent:.1f}% context"
        )

        # Update session state with handoff notes for recovery
        if self._recovery_manager:
            self._recovery_manager.save_session_state(
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
        if self._completion_handler:
            self._completion_handler.record_session(
                session, feature, result,
                outcome=SessionOutcome.HANDOFF,
                commit_hash=commit_hash,
                files_changed=git_status.modified_files + git_status.staged_files
            )

    async def run_coding_session_with_retry(
        self,
        feature: Feature,
        backlog: Backlog,
    ) -> "SessionResult":
        """Run a coding session with automatic retry on transient errors.

        Args:
            feature: The feature to work on
            backlog: The feature backlog

        Returns:
            SessionResult from the final attempt
        """
        from ..session import SessionResult

        retry_config = self.config.retry
        last_result: Optional["SessionResult"] = None

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
            result = await self.run_coding_session(feature, backlog)
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
