"""Session management for the Claude Agent SDK.

Handles invoking the agent, monitoring context usage, and session lifecycle.
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional, Callable, Any

from pydantic import BaseModel

from .models import HarnessConfig, SessionState, Feature


class SessionResult(BaseModel):
    """Result from a completed agent session."""
    session_id: str
    success: bool
    context_usage_percent: float
    error_message: Optional[str] = None
    feature_completed: bool = False
    handoff_requested: bool = False
    summary: Optional[str] = None
    files_changed: list[str] = []


class AgentSession:
    """Manages a single agent session.

    Wraps the Claude Agent SDK to provide:
    - Context usage monitoring
    - Graceful handoff triggers
    - Structured result capture
    """

    def __init__(
        self,
        config: HarnessConfig,
        project_path: Path,
        session_id: Optional[str] = None
    ):
        self.config = config
        self.project_path = Path(project_path)
        self.session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"
        self.context_usage_percent = 0.0
        self._state_file = self.project_path / ".ada_session_state.json"

    def save_state(self, state: SessionState) -> None:
        """Persist session state for recovery."""
        self._state_file.write_text(state.model_dump_json(indent=2))

    def load_state(self) -> Optional[SessionState]:
        """Load previous session state if exists."""
        if not self._state_file.exists():
            return None
        try:
            return SessionState.model_validate_json(self._state_file.read_text())
        except Exception:
            return None

    def clear_state(self) -> None:
        """Clear session state file."""
        if self._state_file.exists():
            self._state_file.unlink()

    async def run(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None
    ) -> SessionResult:
        """Run an agent session with the given prompt.

        Args:
            prompt: The task prompt for the agent
            on_message: Optional callback for streaming messages

        Returns:
            SessionResult with completion status and context usage
        """
        try:
            # Import SDK here to allow graceful failure if not installed
            from claude_agent_sdk import query, ClaudeAgentOptions
        except ImportError:
            # Fallback for development/testing without SDK
            return await self._run_mock_session(prompt, on_message)

        result = SessionResult(
            session_id=self.session_id,
            success=False,
            context_usage_percent=0.0
        )

        try:
            options = ClaudeAgentOptions(
                model=self.config.model,
                allowed_tools=self.config.allowed_tools,
                permission_mode="acceptEdits",
                cwd=str(self.project_path)
            )

            message_count = 0
            async for message in query(prompt=prompt, options=options):
                message_count += 1

                # Track context usage from message metadata
                if hasattr(message, 'usage'):
                    usage = message.usage
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    # Estimate context usage (assuming ~200k context window)
                    total_tokens = input_tokens + output_tokens
                    self.context_usage_percent = (total_tokens / 200000) * 100
                    result.context_usage_percent = self.context_usage_percent

                # Check for handoff trigger
                if self.context_usage_percent >= self.config.context_threshold_percent:
                    result.handoff_requested = True

                # Forward message to callback
                if on_message:
                    on_message(message)

                # Check for ResultMessage (final message type in SDK)
                message_type = type(message).__name__
                if message_type == 'ResultMessage':
                    result.success = not getattr(message, 'is_error', False)
                    if hasattr(message, 'text'):
                        result.summary = message.text
                elif hasattr(message, 'is_final') and message.is_final:
                    result.success = not getattr(message, 'is_error', False)
                    if hasattr(message, 'text'):
                        result.summary = message.text

            # If we processed messages without error, consider it success
            if message_count > 0 and not result.error_message:
                result.success = True

        except Exception as e:
            result.success = False
            result.error_message = str(e)
            import traceback
            print(f"\n[ERROR] Session failed: {e}")
            traceback.print_exc()

        return result

    async def _run_mock_session(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None
    ) -> SessionResult:
        """Mock session for development without the SDK installed."""
        print(f"\n[MOCK SESSION] Would run agent with prompt:\n{prompt[:500]}...")

        # Simulate some work
        await asyncio.sleep(1)

        return SessionResult(
            session_id=self.session_id,
            success=True,
            context_usage_percent=45.0,  # Mock value
            summary="[MOCK] Session completed successfully",
            files_changed=[]
        )


class SessionManager:
    """Manages session lifecycle across the harness.

    Responsibilities:
    - Create and track sessions
    - Handle session recovery
    - Coordinate with progress tracking
    """

    def __init__(self, config: HarnessConfig, project_path: Path):
        self.config = config
        self.project_path = Path(project_path)
        self.current_session: Optional[AgentSession] = None
        self.session_count = 0

    def create_session(self) -> AgentSession:
        """Create a new agent session."""
        self.session_count += 1
        session_id = f"s{self.session_count:03d}_{datetime.now().strftime('%H%M%S')}"
        self.current_session = AgentSession(
            config=self.config,
            project_path=self.project_path,
            session_id=session_id
        )
        return self.current_session

    def should_continue(self) -> bool:
        """Check if we should start another session."""
        if self.config.max_sessions and self.session_count >= self.config.max_sessions:
            return False
        return True

    def get_recovery_state(self) -> Optional[SessionState]:
        """Get state from a previous interrupted session."""
        session = AgentSession(
            config=self.config,
            project_path=self.project_path
        )
        return session.load_state()
