"""Session management for the Claude Agent.

Supports two modes:
- CLI: Direct invocation of `claude` command (uses Claude subscription, reliable)
- SDK: Claude Agent SDK (uses API credits, streaming but less reliable on Windows)
"""

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any, List

from pydantic import BaseModel

from .models import HarnessConfig, SessionState, Feature, SessionMode, ErrorCategory, UsageStats
from .cost_tracker import CostTracker


# Patterns that indicate CLI is waiting for user input
CLI_INPUT_PROMPTS = [
    r"Do you want to proceed\?",
    r"❯\s*\d+\.\s*(Yes|No)",  # Interactive menu
    r"\[y/N\]",
    r"\[Y/n\]",
    r"Press Enter to continue",
    r"Waiting for confirmation",
    r"Allow this action\?",
    r"Permission required",
    r"Type 'yes' to confirm",
]

# Compile patterns for efficiency
CLI_INPUT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CLI_INPUT_PROMPTS]


def detect_input_prompt(text: str) -> Optional[str]:
    """Detect if CLI output contains a prompt waiting for user input.

    Args:
        text: The CLI output text to check

    Returns:
        The matched prompt pattern if found, None otherwise
    """
    for pattern in CLI_INPUT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


class SessionResult(BaseModel):
    """Result from a completed agent session."""
    session_id: str
    success: bool
    context_usage_percent: float
    error_message: Optional[str] = None
    error_category: Optional[ErrorCategory] = None
    feature_completed: bool = False
    handoff_requested: bool = False
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

    # SDK crash / Windows exit code 1 - retry
    if any(phrase in error_lower for phrase in [
        "exit code 1",
        "exit code: 1",
        "exited with code 1"
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


class AgentSession:
    """Manages a single agent session.

    Supports both CLI and SDK modes based on config.
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
        self._cost_tracker = CostTracker(config.model)
        self._started_at: Optional[datetime] = None

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

    def _find_claude_executable(self) -> Optional[str]:
        """Find the claude CLI executable.

        On Windows, npm installs as .cmd files which need special handling.
        Also checks common installation locations.
        """
        # Try shutil.which first (respects PATH)
        claude_path = shutil.which("claude")
        if claude_path:
            return claude_path

        # On Windows, try .cmd extension
        if sys.platform == "win32":
            claude_path = shutil.which("claude.cmd")
            if claude_path:
                return claude_path

            # Check common npm global locations on Windows
            npm_paths = [
                Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
                Path(os.environ.get("LOCALAPPDATA", "")) / "npm" / "claude.cmd",
                Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
            ]
            for p in npm_paths:
                if p.exists():
                    return str(p)

        # On Unix, check common locations
        else:
            unix_paths = [
                Path.home() / ".npm-global" / "bin" / "claude",
                Path("/usr/local/bin/claude"),
                Path.home() / ".local" / "bin" / "claude",
            ]
            for p in unix_paths:
                if p.exists():
                    return str(p)

        return None

    async def run(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None
    ) -> SessionResult:
        """Run an agent session with the given prompt.

        Routes to CLI or SDK based on config.session_mode.
        Applies session timeout if configured.
        """
        timeout = self.config.session_timeout_seconds
        self._started_at = datetime.now()

        try:
            if self.config.session_mode == SessionMode.CLI:
                coro = self._run_cli_session(prompt, on_message)
            else:
                coro = self._run_sdk_session(prompt, on_message)

            # Apply timeout if configured
            if timeout > 0:
                print(f"[SESSION] Timeout set: {timeout}s ({timeout // 60}m)")
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
                error_category=ErrorCategory.TRANSIENT,  # Treat as transient for retry logic
                handoff_requested=True,  # Trigger handoff instead of failure
                summary=f"Session timed out after {timeout // 60} minutes",
                started_at=self._started_at,
                ended_at=datetime.now(),
                model=self.config.model
            )

    async def _run_cli_session(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None
    ) -> SessionResult:
        """Run session using direct CLI invocation with streaming output.

        Uses the user's Claude subscription, not API credits.
        More reliable on Windows than the SDK.

        Features:
        - Streams output in real-time for visibility
        - Detects permission prompts and input requests
        - Per-chunk read timeout to detect stuck processes
        - Graceful handling of blocking scenarios
        """
        result = SessionResult(
            session_id=self.session_id,
            success=False,
            context_usage_percent=0.0
        )

        # Find the claude executable
        claude_path = self._find_claude_executable()
        if not claude_path:
            result.error_message = "Claude CLI not found. Make sure 'claude' is installed and in PATH."
            print(f"\n[ERROR] {result.error_message}")
            return result

        # Per-chunk read timeout (seconds) - if no output for this long, assume stuck
        read_timeout = self.config.cli_read_timeout_seconds

        session_timeout = self.config.session_timeout_seconds

        print(f"\n[CLI] Starting session with model: {self.config.model}")
        print(f"[CLI] Working directory: {self.project_path}")
        print(f"[CLI] Max turns: {self.config.cli_max_turns}")
        print(f"[CLI] Session timeout: {session_timeout}s ({session_timeout // 60}m)")
        print(f"[CLI] Note: CLI buffers output - no streaming until complete")
        print(f"[CLI] Using executable: {claude_path}")
        print(f"[CLI] Prompt length: {len(prompt)} chars")

        try:
            # Write prompt to a temp file for debugging
            import tempfile
            prompt_file = Path(tempfile.gettempdir()) / f"ada_prompt_{self.session_id}.txt"
            prompt_file.write_text(prompt, encoding='utf-8')

            # Build command using stdin for the prompt
            # Use -p - to read from stdin, avoiding shell quoting issues entirely
            cmd_stdin = [
                claude_path,
                "--model", self.config.model,
                "--max-turns", str(self.config.cli_max_turns),
                "--dangerously-skip-permissions",
                "-p", "-",  # Read prompt from stdin
            ]

            print(f"[CLI] Prompt saved to: {prompt_file}")
            print(f"[CLI] Running: {' '.join(cmd_stdin)}")

            # Create environment without ANTHROPIC_API_KEY to force subscription usage
            cli_env = os.environ.copy()
            if "ANTHROPIC_API_KEY" in cli_env:
                del cli_env["ANTHROPIC_API_KEY"]
                print(f"[CLI] Removed ANTHROPIC_API_KEY from environment to use subscription")

            # Run claude CLI with separate stdout/stderr streams
            process = await asyncio.create_subprocess_exec(
                *cmd_stdin,
                cwd=str(self.project_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=cli_env,
            )

            # Send prompt via stdin and close stdin to signal end of input
            process.stdin.write(prompt.encode('utf-8'))
            await process.stdin.drain()
            process.stdin.close()
            await process.stdin.wait_closed()

            print(f"[CLI] Prompt sent, reading output with {read_timeout}s timeout per chunk...")

            # Stream output with per-read timeout to detect blocking
            stdout_chunks: List[str] = []
            stderr_chunks: List[str] = []
            last_output_time = datetime.now()
            detected_prompt = None
            recent_output = ""  # Buffer for prompt detection

            async def read_stream_with_timeout(stream, chunks: List[str], stream_name: str):
                """Read from a stream with timeout detection.

                Note: Claude CLI buffers output when stdout is a pipe, so we may not
                see any output until the process completes. This is normal behavior.

                We only terminate early if:
                1. We detected a permission prompt AND
                2. No output followed for read_timeout seconds

                Otherwise, we let the session timeout (30 min default) handle it.
                """
                nonlocal last_output_time, detected_prompt, recent_output
                timeout_warnings = 0

                while True:
                    try:
                        # Read with timeout
                        chunk = await asyncio.wait_for(
                            stream.read(4096),
                            timeout=read_timeout
                        )

                        if not chunk:
                            # Stream ended
                            break

                        text = chunk.decode('utf-8', errors='replace')
                        chunks.append(text)
                        last_output_time = datetime.now()
                        timeout_warnings = 0  # Reset warning counter on output

                        # Print output in real-time
                        if stream_name == "stdout":
                            print(text, end='', flush=True)

                            # Buffer recent output for prompt detection
                            recent_output += text
                            # Keep only last 1000 chars for detection
                            if len(recent_output) > 1000:
                                recent_output = recent_output[-1000:]

                            # Check for input prompts
                            prompt_match = detect_input_prompt(recent_output)
                            if prompt_match and not detected_prompt:
                                detected_prompt = prompt_match
                                print(f"\n\n[CLI WARNING] Detected input prompt: '{prompt_match}'")
                                print(f"[CLI WARNING] CLI may be waiting for user input!")
                                # Don't break - let the timeout handle it

                    except asyncio.TimeoutError:
                        # No output for read_timeout seconds
                        elapsed = (datetime.now() - last_output_time).total_seconds()
                        timeout_warnings += 1

                        # Check if process is still running
                        if process.returncode is not None:
                            break

                        # Only warn periodically (every 2 timeouts = 4 min by default)
                        if timeout_warnings % 2 == 1:
                            print(f"\n[CLI INFO] No output for {elapsed:.0f}s (CLI buffers output, this is normal)")

                        # ONLY abort if we detected a permission prompt
                        # This means the CLI is waiting for input
                        if detected_prompt:
                            print(f"[CLI ERROR] Process stuck on input prompt: '{detected_prompt}'")
                            return "stuck_on_prompt"

                        # Otherwise, continue waiting - let session timeout handle it
                        # The session timeout (default 30 min) is the primary safeguard

                return "ok"

            # Read stdout and stderr concurrently
            stdout_task = asyncio.create_task(
                read_stream_with_timeout(process.stdout, stdout_chunks, "stdout")
            )
            stderr_task = asyncio.create_task(
                read_stream_with_timeout(process.stderr, stderr_chunks, "stderr")
            )

            # Wait for both to complete
            stdout_status, stderr_status = await asyncio.gather(stdout_task, stderr_task)

            # Clean up temp file
            try:
                prompt_file.unlink()
            except:
                pass

            # Check if we got stuck on a permission prompt
            if stdout_status == "stuck_on_prompt":
                print(f"\n[CLI] Terminating process stuck on permission prompt...")
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    print(f"[CLI] Force killing process...")
                    process.kill()
                    await process.wait()

                result.error_message = f"CLI stuck waiting for input: '{detected_prompt}'"
                result.error_category = ErrorCategory.TRANSIENT
                result.success = False
                result.raw_output = "".join(stdout_chunks)
                result.raw_error = "".join(stderr_chunks)
                return result

            # Wait for process to complete
            await process.wait()

            stdout_text = "".join(stdout_chunks)
            stderr_text = "".join(stderr_chunks)

            # Store raw output for debugging
            result.raw_output = stdout_text
            result.raw_error = stderr_text

            # Debug: Show what we got back
            print(f"\n\n[CLI DEBUG] Return code: {process.returncode}")
            print(f"[CLI DEBUG] Stdout length: {len(stdout_text)} chars")
            print(f"[CLI DEBUG] Stderr length: {len(stderr_text)} chars")
            if stderr_text:
                print(f"[CLI DEBUG] Stderr: {stderr_text[:500]}")
            if not stdout_text and not stderr_text:
                print(f"[CLI DEBUG] No output received from CLI!")

            # Check for errors
            if process.returncode != 0:
                error_text = stderr_text or stdout_text
                result.error_category = classify_error(error_text)
                result.error_message = f"CLI exited with code {process.returncode}: {error_text.strip()[:500]}"

                if result.error_category == ErrorCategory.BILLING:
                    print(f"\n[ERROR] API credits issue: {error_text}")
                elif result.error_category == ErrorCategory.RATE_LIMIT:
                    print(f"\n[ERROR] Rate limited: {error_text}")
                elif result.error_category == ErrorCategory.AUTH:
                    print(f"\n[ERROR] Authentication issue: {error_text}")
                else:
                    print(f"\n[ERROR] CLI failed (code {process.returncode}) - {result.error_category.value}")

                result.success = False
            else:
                result.success = True
                result.summary = "Session completed successfully via CLI"
                print(f"\n[CLI] Session completed successfully")

                # Try to parse usage stats from CLI output
                parsed_stats = CostTracker.parse_cli_output(stdout_text)
                if parsed_stats:
                    if parsed_stats.input_tokens or parsed_stats.output_tokens:
                        parsed_stats.cost_usd = self._cost_tracker.calculate_cost(
                            input_tokens=parsed_stats.input_tokens,
                            output_tokens=parsed_stats.output_tokens,
                            cache_read_tokens=parsed_stats.cache_read_tokens,
                            cache_write_tokens=parsed_stats.cache_write_tokens
                        )
                        parsed_stats.model = self.config.model
                    result.usage_stats = parsed_stats
                    print(f"[CLI] Usage: {parsed_stats.input_tokens} in / {parsed_stats.output_tokens} out (${parsed_stats.cost_usd:.4f})")

        except FileNotFoundError:
            result.error_message = "Claude CLI not found. Make sure 'claude' is installed and in PATH."
            print(f"\n[ERROR] {result.error_message}")
        except Exception as e:
            result.error_message = f"CLI session error: {str(e)}"
            print(f"\n[ERROR] {result.error_message}")
            import traceback
            traceback.print_exc()

        return result

    async def _run_sdk_session(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None
    ) -> SessionResult:
        """Run session using Claude Agent SDK.

        Note: Uses API credits, not Claude subscription.
        Known to have reliability issues on Windows.
        """
        try:
            # Import SDK here to allow graceful failure if not installed
            from claude_agent_sdk import query, ClaudeAgentOptions
        except ImportError:
            return await self._run_mock_session(prompt, on_message)

        result = SessionResult(
            session_id=self.session_id,
            success=False,
            context_usage_percent=0.0
        )

        # Track message processing
        message_count = 0
        received_result_message = False
        all_messages = []  # Capture all messages for debugging
        total_input_tokens = 0
        total_output_tokens = 0

        print(f"\n[SDK] Starting session with model: {self.config.model}")
        print(f"[SDK] NOTE: SDK uses API credits, not your Claude subscription")
        print(f"[SDK] Working directory: {self.project_path}")
        print(f"[SDK] Allowed tools: {', '.join(self.config.allowed_tools)}")
        print(f"[SDK] Prompt length: {len(prompt)} chars")
        print(f"\n{'='*60}")
        print("[SDK] Waiting for messages from Claude Agent SDK...")
        print(f"{'='*60}\n")

        try:
            options = ClaudeAgentOptions(
                model=self.config.model,
                allowed_tools=self.config.allowed_tools,
                permission_mode="acceptEdits",
                cwd=str(self.project_path)
            )

            async for message in query(prompt=prompt, options=options):
                message_count += 1

                # Capture message for debugging
                msg_type = type(message).__name__
                msg_text = getattr(message, 'text', None) or getattr(message, 'content', None) or str(message)
                all_messages.append(f"[{msg_type}] {msg_text[:200] if msg_text else '(no text)'}")

                # === VERBOSE LOGGING ===
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{timestamp}] Message #{message_count}: {msg_type}")

                # Show text content (truncated)
                if msg_text and isinstance(msg_text, str):
                    display_text = msg_text[:300] + "..." if len(msg_text) > 300 else msg_text
                    # Clean up for display
                    display_text = display_text.replace('\n', ' ').strip()
                    if display_text:
                        print(f"  Content: {display_text}")

                # Show tool usage if present
                if hasattr(message, 'tool_name'):
                    print(f"  Tool: {message.tool_name}")
                if hasattr(message, 'tool_input'):
                    tool_input = str(message.tool_input)[:200]
                    print(f"  Input: {tool_input}...")
                if hasattr(message, 'tool_result'):
                    tool_result = str(message.tool_result)[:200]
                    print(f"  Result: {tool_result}...")

                # Show any error info
                if hasattr(message, 'is_error') and message.is_error:
                    print(f"  ERROR: {getattr(message, 'error', 'Unknown error')}")

                # Track context usage from message metadata
                if hasattr(message, 'usage'):
                    usage = message.usage
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    total_tokens = total_input_tokens + total_output_tokens
                    self.context_usage_percent = (total_tokens / 200000) * 100
                    result.context_usage_percent = self.context_usage_percent
                    print(f"  Tokens: {input_tokens} in / {output_tokens} out ({self.context_usage_percent:.1f}% context)")

                # Check for handoff trigger
                if self.context_usage_percent >= self.config.context_threshold_percent:
                    result.handoff_requested = True
                    print(f"  [!] Context threshold reached - handoff requested")

                # Forward message to callback
                if on_message:
                    on_message(message)

                # Check for ResultMessage
                if msg_type == 'ResultMessage':
                    received_result_message = True
                    is_error = getattr(message, 'is_error', False)
                    result.success = not is_error
                    if hasattr(message, 'text'):
                        result.summary = message.text
                    # Check for error content in the result
                    if is_error and hasattr(message, 'text'):
                        result.error_message = message.text
                        print(f"\n[SDK ERROR] Agent returned error: {message.text}")
                    else:
                        print(f"\n[SDK] ResultMessage received - session completing")
                elif hasattr(message, 'is_final') and message.is_final:
                    received_result_message = True
                    is_error = getattr(message, 'is_error', False)
                    result.success = not is_error
                    if hasattr(message, 'text'):
                        result.summary = message.text
                    print(f"\n[SDK] Final message received")

            # Store message log for debugging
            result.raw_output = "\n".join(all_messages)

            # Calculate and store usage stats
            if total_input_tokens or total_output_tokens:
                cost = self._cost_tracker.calculate_cost(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens
                )
                result.usage_stats = UsageStats(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    model=self.config.model,
                    cost_usd=cost
                )
                print(f"[SDK] Total usage: {total_input_tokens} in / {total_output_tokens} out (${cost:.4f})")

            print(f"\n{'='*60}")
            print(f"[SDK] Session completed - processed {message_count} messages")
            print(f"{'='*60}\n")

            # If we processed messages without error, consider it success
            if message_count > 0 and not result.error_message:
                result.success = True

        except Exception as e:
            error_str = str(e)

            # Store the raw error
            result.raw_error = error_str

            # Classify the error for retry logic
            result.error_category = classify_error(error_str)

            # Always log the full error for visibility
            print(f"\n[SDK ERROR] Exception during session:")
            print(f"[SDK ERROR] {error_str}")
            print(f"[SDK ERROR] Category: {result.error_category.value}")

            # Display category-specific messages
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
                # Windows SDK bug - but now we have more context
                print(f"\n[SDK] Exit code 1 encountered")
                print(f"[SDK] Messages received before error: {message_count}")
                if all_messages:
                    print(f"[SDK] Last few messages:")
                    for msg in all_messages[-3:]:
                        print(f"  {msg}")

                if received_result_message and message_count > 0:
                    print(f"[SDK] Received ResultMessage - session may have completed")
                    result.error_message = "Session ended with exit code 1 - status uncertain, review changes"
                else:
                    result.error_message = f"SDK crashed with exit code 1 before completing: {error_str}"
            else:
                result.error_message = f"SDK Error: {error_str}"

            result.success = False

            # Print full traceback for debugging
            import traceback
            print("\n[SDK] Full traceback:")
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
            context_usage_percent=45.0,
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
