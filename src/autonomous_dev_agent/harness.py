"""Main harness orchestrator for autonomous development.

This is the core engine that:
1. Loads the backlog
2. Runs initialization (first time only)
3. Loops through sessions until backlog is complete
4. Handles handoffs between sessions
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import (
    Backlog, Feature, FeatureStatus, HarnessConfig,
    SessionState, ProgressEntry
)
from .progress import ProgressTracker
from .git_manager import GitManager
from .session import SessionManager, AgentSession, SessionResult


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
        self.progress = ProgressTracker(self.project_path, self.config.progress_file)
        self.git = GitManager(self.project_path)
        self.sessions = SessionManager(self.config, self.project_path)

        # State
        self.initialized = False
        self.total_sessions = 0

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
        console.print(Panel(
            f"[bold green]Feature:[/bold green] {feature.name}\n"
            f"[dim]{feature.description}[/dim]",
            title="Coding Session"
        ))

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
            acceptance_criteria=self._format_acceptance_criteria(feature)
        )

        # Log session start
        session = self.sessions.create_session()
        self.progress.log_session_start(session.session_id, feature)

        # Run the agent
        result = await session.run(prompt, on_message=self._on_message)

        # Handle result
        if result.handoff_requested:
            await self._perform_handoff(session, feature, result)
        elif result.feature_completed or result.success:
            self._complete_feature(session, feature, result)

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

        console.print(f"[green]OK[/green] Handoff complete. Commit: {commit_hash or 'no changes'}")

    def _complete_feature(
        self,
        session: AgentSession,
        feature: Feature,
        result: SessionResult
    ) -> None:
        """Mark a feature as completed."""
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

        console.print(f"[green]OK[/green] Feature completed: {feature.name}")

    def _on_message(self, message: Any) -> None:
        """Handle streaming messages from the agent."""
        # For now, just print text messages
        if hasattr(message, 'text'):
            console.print(message.text, end="")

    async def run(self) -> None:
        """Main entry point - run until backlog is complete."""
        console.print(Panel(
            f"[bold]Autonomous Development Agent[/bold]\n"
            f"Project: {self.project_path.name}",
            title="ADA Harness"
        ))

        # Load backlog
        try:
            self.load_backlog()
        except FileNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            return

        console.print(f"Loaded {len(self.backlog.features)} features")

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
            feature = self.backlog.get_next_feature()

            if not feature:
                console.print("[yellow]No eligible features to work on (check dependencies)[/yellow]")
                break

            console.print(f"\n{'='*60}")
            console.print(f"Session {self.total_sessions + 1}")
            console.print(f"{'='*60}")

            result = await self.run_coding_session(feature)
            self.total_sessions += 1

            if not result.success and not result.handoff_requested:
                console.print(f"[red]Session failed: {result.error_message}[/red]")
                # Continue to next feature or retry logic could go here
                continue

            # Brief pause between sessions
            await asyncio.sleep(2)

        # Summary
        completed = sum(1 for f in self.backlog.features if f.status == FeatureStatus.COMPLETED)
        console.print(Panel(
            f"[bold]Sessions run:[/bold] {self.total_sessions}\n"
            f"[bold]Features completed:[/bold] {completed}/{len(self.backlog.features)}",
            title="Summary"
        ))


async def run_harness(
    project_path: str,
    config: Optional[HarnessConfig] = None
) -> None:
    """Convenience function to run the harness."""
    harness = AutonomousHarness(project_path, config)
    await harness.run()
