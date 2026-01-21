"""Session management for the Claude Agent.

Uses the Claude Agent SDK for agent sessions with API credits.

Architecture:
- BaseSession: Abstract base class with common session logic
- SDKSession: SDK-specific implementation
- MockSession: For testing without SDK installed
- create_session(): Factory function to create SDK sessions
"""

import asyncio
import json
import os
import sys
import uuid
import warnings
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any

from pydantic import BaseModel

from .models import (
    HarnessConfig, SessionState, Feature, ErrorCategory, UsageStats,
    AssistantMessageEvent, ToolResultEvent
)
from .token_tracker import TokenTracker, format_tokens


# Global flag to track if we're in graceful shutdown mode
_graceful_shutdown_in_progress = False


def _sdk_exception_handler(loop, context):
    """Custom exception handler for asyncio to suppress SDK cleanup errors during shutdown."""
    global _graceful_shutdown_in_progress

    exception = context.get('exception')
    message = context.get('message', '')

    # During graceful shutdown, suppress known SDK cleanup errors
    if _graceful_shutdown_in_progress:
        error_str = str(exception) if exception else message

        # Suppress anyio cancel scope errors (SDK cleanup issue)
        if 'cancel scope' in error_str.lower():
            return  # Silently suppress

        # Suppress generator cleanup errors
        if isinstance(exception, (GeneratorExit, RuntimeError)):
            if 'cancel scope' in error_str or 'generator' in error_str.lower():
                return  # Silently suppress

    # For other errors, use the default handler
    loop.default_exception_handler(context)


def safe_print(text: str, **kwargs) -> None:
    """Print text handling Unicode encoding errors on Windows.

    Windows cp1252 encoding can't handle many Unicode characters (emojis, etc).
    This function falls back to replacing unencodable characters with '?'.
    Always flushes to ensure output is visible immediately.
    """
    kwargs.setdefault('flush', True)
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        # Windows cp1252 can't handle some Unicode chars
        safe_text = text.encode('ascii', errors='replace').decode('ascii')
        print(safe_text, **kwargs)


# =============================================================================
# Session Result Model
# =============================================================================

class SessionResult(BaseModel):
    """Result from a completed agent session."""
    session_id: str
    success: bool
    context_usage_percent: float
    error_message: Optional[str] = None
    error_category: Optional[ErrorCategory] = None
    feature_completed: bool = False
    handoff_requested: bool = False
    interrupted: bool = False  # True if session was interrupted by stop request
    summary: Optional[str] = None
    files_changed: list[str] = []
    # Token usage and cost tracking
    usage_stats: UsageStats = UsageStats()
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    model: str = ""
    # Capture raw output for debugging
    raw_output: Optional[str] = None
    raw_error: Optional[str] = None


# =============================================================================
# Error Classification
# =============================================================================

def classify_error(error_text: str) -> ErrorCategory:
    """Classify an error message to determine retry strategy.

    Args:
        error_text: The error message or output to classify

    Returns:
        ErrorCategory indicating what type of error occurred
    """
    if not error_text:
        return ErrorCategory.UNKNOWN

    error_lower = error_text.lower()

    # Billing/credit errors - non-recoverable
    if any(phrase in error_lower for phrase in [
        "credit balance",
        "insufficient credits",
        "billing",
        "payment required",
        "quota exceeded"
    ]):
        return ErrorCategory.BILLING

    # Authentication errors - non-recoverable
    if any(phrase in error_lower for phrase in [
        "authentication",
        "unauthorized",
        "401",
        "invalid api key",
        "api key",
        "forbidden",
        "403"
    ]):
        return ErrorCategory.AUTH

    # Rate limit errors - retry with longer delay
    if any(phrase in error_lower for phrase in [
        "rate limit",
        "429",
        "too many requests",
        "throttl"
    ]):
        return ErrorCategory.RATE_LIMIT

    # SDK crash / Windows exit codes - retry
    if any(phrase in error_lower for phrase in [
        "exit code 1",
        "exit code: 1",
        "exited with code 1",
        # Windows heap corruption (0xC0000374 = 3221225786)
        "exit code 3221225786",
        "exit code: 3221225786",
        "exited with code 3221225786",
        "0xc0000374",
        "heap corruption",
    ]):
        return ErrorCategory.SDK_CRASH

    # Transient network/timeout errors - retry
    if any(phrase in error_lower for phrase in [
        "timeout",
        "timed out",
        "connection",
        "network",
        "unreachable",
        "temporarily unavailable",
        "500",
        "502",
        "503",
        "504",
        "internal server error",
        "service unavailable",
        "gateway"
    ]):
        return ErrorCategory.TRANSIENT

    return ErrorCategory.UNKNOWN


# =============================================================================
# Base Session Class (Abstract)
# =============================================================================

class BaseSession(ABC):
    """Abstract base class for agent sessions.

    Provides common functionality:
    - Session state persistence
    - Timeout handling
    - Token tracking setup

    Subclasses implement the actual session execution logic.
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
        self._state_file = self._get_state_file_path()
        self._token_tracker = TokenTracker(config.model)
        self._started_at: Optional[datetime] = None

    def _get_state_file_path(self) -> Path:
        """Get the state file path with backward compatibility.

        New location: .ada/state/session.json
        Legacy location: .ada_session_state.json

        Returns new location if .ada/ exists, otherwise legacy location.
        """
        new_path = self.project_path / ".ada" / "state" / "session.json"
        legacy_path = self.project_path / ".ada_session_state.json"

        # Check if legacy file exists first (takes precedence for backward compat)
        if legacy_path.exists():
            return legacy_path

        # If .ada/ workspace exists, use new location
        if (self.project_path / ".ada").exists():
            # Ensure state directory exists
            new_path.parent.mkdir(parents=True, exist_ok=True)
            return new_path

        # Default to legacy location for projects without .ada/
        return legacy_path

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
        on_message: Optional[Callable[[Any], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> SessionResult:
        """Run an agent session with the given prompt.

        Applies session timeout if configured, then delegates to
        the subclass-specific _run_session implementation.

        Args:
            prompt: The prompt to send to the agent
            on_message: Optional callback for streaming messages
            stop_check: Optional callback that returns True if stop was requested.
                       When stop is detected, the session will gracefully interrupt.
        """
        timeout = self.config.session_timeout_seconds
        self._started_at = datetime.now()

        try:
            coro = self._run_session(prompt, on_message, stop_check)

            # Apply timeout if configured
            if timeout > 0:
                print(f"[SESSION] Timeout set: {timeout}s ({timeout // 60}m)", flush=True)
                result = await asyncio.wait_for(coro, timeout=timeout)
            else:
                result = await coro

            # Add timing and model info
            result.started_at = self._started_at
            result.ended_at = datetime.now()
            result.model = self.config.model

            return result

        except asyncio.TimeoutError:
            print(f"\n[SESSION] Timeout after {timeout}s - forcing handoff")
            return SessionResult(
                session_id=self.session_id,
                success=False,
                context_usage_percent=self.context_usage_percent,
                error_message=f"Session timeout after {timeout}s - forcing handoff",
                error_category=ErrorCategory.TRANSIENT,
                handoff_requested=True,
                summary=f"Session timed out after {timeout // 60} minutes",
                started_at=self._started_at,
                ended_at=datetime.now(),
                model=self.config.model
            )

    @abstractmethod
    async def _run_session(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> SessionResult:
        """Execute the session - implemented by subclasses.

        Args:
            prompt: The prompt to send to the agent
            on_message: Optional callback for streaming messages
            stop_check: Optional callback that returns True if stop was requested
        """
        pass


# =============================================================================
# SDK Session Implementation
# =============================================================================

class SDKSession(BaseSession):
    """Session implementation using Claude Agent SDK.

    Uses API credits for billing. Provides real-time streaming of agent messages,
    token usage tracking, and context usage monitoring for handoff triggers.
    """

    async def _run_session(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> SessionResult:
        """Run session using Claude Agent SDK."""
        global _graceful_shutdown_in_progress
        print("[SDK] Entering _run_session...", flush=True)

        # Set up custom exception handler to suppress SDK cleanup errors during shutdown
        loop = asyncio.get_event_loop()
        original_handler = loop.get_exception_handler()
        loop.set_exception_handler(_sdk_exception_handler)

        try:
            print("[SDK] Importing claude_agent_sdk...", flush=True)
            from claude_agent_sdk import query, ClaudeAgentOptions
            print("[SDK] Import successful", flush=True)
        except ImportError as e:
            print(f"[SDK] Import failed: {e}, falling back to mock", flush=True)
            # Restore original handler before returning
            if original_handler:
                loop.set_exception_handler(original_handler)
            else:
                loop.set_exception_handler(None)
            # Fall back to mock if SDK not installed
            return await self._run_mock_session(prompt, on_message, stop_check)

        result = SessionResult(
            session_id=self.session_id,
            success=False,
            context_usage_percent=0.0
        )

        message_count = 0
        received_result_message = False
        all_messages = []
        files_changed_set: set[str] = set()  # Track unique files modified
        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_read_tokens = 0
        total_cache_write_tokens = 0

        print(f"\n[SDK] Starting session with model: {self.config.model}", flush=True)
        print(f"[SDK] NOTE: SDK uses API credits, not your Claude subscription", flush=True)
        print(f"[SDK] Working directory: {self.project_path}", flush=True)
        print(f"[SDK] Allowed tools: {', '.join(self.config.allowed_tools)}", flush=True)
        print(f"[SDK] Prompt length: {len(prompt)} chars", flush=True)
        print(f"\n{'='*60}", flush=True)
        print("[SDK] Waiting for messages from Claude Agent SDK...", flush=True)
        print(f"{'='*60}\n", flush=True)

        try:
            options = ClaudeAgentOptions(
                model=self.config.model,
                allowed_tools=self.config.allowed_tools,
                permission_mode="acceptEdits",
                cwd=str(self.project_path)
            )

            # Track if we break early for proper cleanup messaging
            interrupted_early = False

            async for message in query(prompt=prompt, options=options):
                message_count += 1
                msg_type = type(message).__name__
                timestamp = datetime.now().strftime("%H:%M:%S")

                # Extract data from message - SDK uses 'data' dict
                data = getattr(message, 'data', {}) or {}
                msg_text = (
                    getattr(message, 'text', None) or
                    getattr(message, 'content', None) or
                    data.get('text') or
                    data.get('content') or
                    ''
                )

                # Get tool info from data
                tool_name = data.get('tool_name') or data.get('tool') or getattr(message, 'tool_name', None)
                tool_input = data.get('tool_input') or data.get('input') or getattr(message, 'tool_input', None)
                tool_result = data.get('tool_result') or data.get('result') or getattr(message, 'tool_result', None)

                all_messages.append(f"[{msg_type}] {str(msg_text)[:200] if msg_text else '(no text)'}")

                # Format display based on message type and emit structured events
                if 'Assistant' in msg_type:
                    if tool_name:
                        print(f"\n[{timestamp}] Tool: {tool_name}", flush=True)
                        if tool_input:
                            input_str = str(tool_input)[:300]
                            safe_print(f"  Input: {input_str}")

                        # Emit AssistantMessageEvent with tool call info
                        if on_message:
                            tool_call_id = data.get('tool_call_id') or data.get('id') or f"tc_{message_count}"
                            tool_calls = [{
                                "id": tool_call_id,
                                "name": tool_name,
                                "input": tool_input or {}
                            }]
                            event = AssistantMessageEvent(
                                content=str(msg_text) if msg_text else "",
                                tool_calls=tool_calls
                            )
                            on_message(event)
                    elif msg_text:
                        print(f"\n[{timestamp}] Claude:", flush=True)
                        display_text = str(msg_text)[:500].replace('\n', '\n  ')
                        safe_print(f"  {display_text}")

                        # Emit AssistantMessageEvent for text content
                        if on_message:
                            event = AssistantMessageEvent(
                                content=str(msg_text)
                            )
                            on_message(event)
                    else:
                        print(f"\n[{timestamp}] {msg_type}", flush=True)
                elif 'User' in msg_type:
                    if tool_result:
                        result_str = str(tool_result)[:200]
                        safe_print(f"  Result: {result_str}...")

                        # Determine file changed if it's a file-modifying tool
                        file_changed = None
                        if tool_name in ('Write', 'Edit', 'NotebookEdit'):
                            file_changed = (
                                (tool_input or {}).get('file_path') or
                                (tool_input or {}).get('path')
                            )
                            # Track for milestone commits
                            if file_changed:
                                files_changed_set.add(file_changed)

                        # Emit ToolResultEvent
                        if on_message:
                            tool_call_id = data.get('tool_call_id') or data.get('id') or f"tc_{message_count}"
                            event = ToolResultEvent(
                                tool_call_id=tool_call_id,
                                tool=tool_name or "unknown",
                                input_data=tool_input or {},
                                output=str(tool_result),
                                file_changed=file_changed
                            )
                            on_message(event)
                    # Skip printing empty user messages
                elif 'System' in msg_type:
                    subtype = data.get('subtype', '')
                    print(f"\n[{timestamp}] System: {subtype}", flush=True)
                elif 'Result' in msg_type:
                    print(f"\n[{timestamp}] {msg_type}: {msg_text[:200] if msg_text else 'done'}", flush=True)
                else:
                    print(f"\n[{timestamp}] {msg_type}", flush=True)
                    if msg_text:
                        safe_print(f"  {str(msg_text)[:200]}")

                if hasattr(message, 'is_error') and message.is_error:
                    safe_print(f"  ERROR: {getattr(message, 'error', data.get('error', 'Unknown error'))}")

                if hasattr(message, 'usage'):
                    usage = message.usage
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    cache_read_tokens = usage.get('cache_read_input_tokens', 0)
                    cache_write_tokens = usage.get('cache_creation_input_tokens', 0)
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    total_cache_read_tokens += cache_read_tokens
                    total_cache_write_tokens += cache_write_tokens
                    total_tokens = total_input_tokens + total_output_tokens
                    self.context_usage_percent = (total_tokens / 200000) * 100
                    result.context_usage_percent = self.context_usage_percent
                    cache_info = f" (cache: {cache_read_tokens}r/{cache_write_tokens}w)" if cache_read_tokens or cache_write_tokens else ""
                    print(f"  Tokens: {input_tokens} in / {output_tokens} out{cache_info} ({self.context_usage_percent:.1f}% context)")

                if self.context_usage_percent >= self.config.context_threshold_percent:
                    result.handoff_requested = True
                    print(f"  [!] Context threshold reached - handoff requested")

                # Check for stop request (mid-session interruption)
                if stop_check and stop_check():
                    _graceful_shutdown_in_progress = True
                    print(f"\n[SDK] Stop requested - interrupting session gracefully")
                    result.interrupted = True
                    result.summary = f"Session interrupted by stop request after {message_count} messages"
                    interrupted_early = True
                    break

                if on_message:
                    on_message(message)

                if msg_type == 'ResultMessage':
                    received_result_message = True
                    is_error = getattr(message, 'is_error', False)
                    result.success = not is_error
                    if hasattr(message, 'text'):
                        result.summary = message.text
                    if is_error and hasattr(message, 'text'):
                        result.error_message = message.text
                        safe_print(f"\n[SDK ERROR] Agent returned error: {message.text}")
                    else:
                        print(f"\n[SDK] ResultMessage received - session completing")
                elif hasattr(message, 'is_final') and message.is_final:
                    received_result_message = True
                    is_error = getattr(message, 'is_error', False)
                    result.success = not is_error
                    if hasattr(message, 'text'):
                        result.summary = message.text
                    print(f"\n[SDK] Final message received")

            result.raw_output = "\n".join(all_messages)
            result.files_changed = list(files_changed_set)

            if total_input_tokens or total_output_tokens:
                result.usage_stats = UsageStats(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    cache_read_tokens=total_cache_read_tokens,
                    cache_write_tokens=total_cache_write_tokens,
                    model=self.config.model,
                )
                cache_info = f" (cache: {total_cache_read_tokens}r/{total_cache_write_tokens}w)" if total_cache_read_tokens or total_cache_write_tokens else ""
                total_tokens = total_input_tokens + total_output_tokens
                print(f"[SDK] Total usage: {format_tokens(total_input_tokens)} in / {format_tokens(total_output_tokens)} out{cache_info} ({format_tokens(total_tokens)} total)")

            print(f"\n{'='*60}")
            print(f"[SDK] Session completed - processed {message_count} messages")
            print(f"{'='*60}\n")

            if message_count > 0 and not result.error_message:
                result.success = True

        except GeneratorExit:
            # This happens when we break out of the async for loop
            # The generator cleanup is expected, not an error
            if interrupted_early:
                print(f"[SDK] Generator cleanup after early exit (expected)")
            pass
        except RuntimeError as e:
            # The SDK's anyio-based cleanup can throw this when breaking out of the loop
            # "Attempted to exit cancel scope in a different task than it was entered in"
            if "cancel scope" in str(e) and interrupted_early:
                print(f"[SDK] Async cleanup error suppressed (expected during interruption)")
            else:
                # Re-raise if it's not the expected cleanup error
                raise
        except Exception as e:
            error_str = str(e)
            result.raw_error = error_str
            result.error_category = classify_error(error_str)

            safe_print(f"\n[SDK ERROR] Exception during session:")
            safe_print(f"[SDK ERROR] {error_str}")
            print(f"[SDK ERROR] Category: {result.error_category.value}")

            if result.error_category == ErrorCategory.BILLING:
                print(f"\n{'='*60}")
                print("[BILLING ERROR] Credit balance is too low!")
                print("The SDK uses Anthropic API credits, NOT your Claude subscription.")
                print("Options:")
                print("  1. Add credits at console.anthropic.com")
                print("  2. Use CLI mode instead (uses your subscription)")
                print(f"{'='*60}\n")
                result.error_message = "API Credit Error: Credit balance is too low. SDK uses API credits, not Claude subscription."
            elif result.error_category == ErrorCategory.RATE_LIMIT:
                print(f"\n[RATE LIMIT] Too many requests - will retry with backoff")
                result.error_message = f"Rate Limited: {error_str}"
            elif result.error_category == ErrorCategory.AUTH:
                print(f"\n[AUTH ERROR] Authentication failed")
                result.error_message = f"Auth Error: {error_str}"
            elif result.error_category == ErrorCategory.SDK_CRASH:
                print(f"\n[SDK] Exit code 1 encountered")
                print(f"[SDK] Messages received before error: {message_count}")
                if all_messages:
                    print(f"[SDK] Last few messages:")
                    for msg in all_messages[-3:]:
                        safe_print(f"  {msg}")

                if received_result_message and message_count > 0:
                    print(f"[SDK] Received ResultMessage - session may have completed")
                    result.error_message = "Session ended with exit code 1 - status uncertain, review changes"
                else:
                    result.error_message = f"SDK crashed with exit code 1 before completing: {error_str}"
            else:
                result.error_message = f"SDK Error: {error_str}"

            result.success = False

            import traceback
            print("\n[SDK] Full traceback:")
            traceback.print_exc()
        finally:
            # Restore the original exception handler
            _graceful_shutdown_in_progress = False
            if original_handler:
                loop.set_exception_handler(original_handler)
            else:
                loop.set_exception_handler(None)

        return result

    async def _run_mock_session(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> SessionResult:
        """Mock session for development without the SDK installed."""
        print(f"\n[MOCK SESSION] Would run agent with prompt:\n{prompt[:500]}...")
        await asyncio.sleep(1)

        # Check for stop request
        if stop_check and stop_check():
            return SessionResult(
                session_id=self.session_id,
                success=False,
                context_usage_percent=45.0,
                summary="[MOCK] Session interrupted by stop request",
                interrupted=True,
                files_changed=[]
            )

        return SessionResult(
            session_id=self.session_id,
            success=True,
            context_usage_percent=45.0,
            summary="[MOCK] Session completed successfully",
            files_changed=[]
        )


# =============================================================================
# Mock Session (for testing)
# =============================================================================

class MockSession(BaseSession):
    """Mock session for testing without any external dependencies."""

    async def _run_session(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> SessionResult:
        """Run a mock session that simulates success."""
        print(f"\n[MOCK SESSION] Simulating session with prompt ({len(prompt)} chars)")
        await asyncio.sleep(0.5)

        # Check for stop request
        if stop_check and stop_check():
            return SessionResult(
                session_id=self.session_id,
                success=False,
                context_usage_percent=25.0,
                summary="[MOCK] Session interrupted by stop request",
                interrupted=True,
                files_changed=[]
            )

        return SessionResult(
            session_id=self.session_id,
            success=True,
            context_usage_percent=25.0,
            summary="[MOCK] Session completed successfully",
            files_changed=[]
        )


# =============================================================================
# Factory Function
# =============================================================================

def create_session(
    config: HarnessConfig,
    project_path: Path,
    session_id: Optional[str] = None
) -> BaseSession:
    """Factory function to create an SDK session.

    Args:
        config: Harness configuration
        project_path: Path to the project directory
        session_id: Optional session identifier

    Returns:
        SDKSession instance
    """
    return SDKSession(config, project_path, session_id)


# =============================================================================
# Session Manager
# =============================================================================

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
        self.current_session: Optional[BaseSession] = None
        self.session_count = 0

    def create_session(self) -> BaseSession:
        """Create a new agent session using the appropriate implementation."""
        self.session_count += 1
        session_id = f"s{self.session_count:03d}_{datetime.now().strftime('%H%M%S')}"
        self.current_session = create_session(
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
        # Use a temporary session just to read state
        temp_session = SDKSession(
            config=self.config,
            project_path=self.project_path
        )
        return temp_session.load_state()
