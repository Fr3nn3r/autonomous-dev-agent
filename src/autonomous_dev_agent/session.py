"""Session management for the Claude Agent.

Supports two modes:
- CLI: Direct invocation of `claude` command (uses Claude subscription, reliable)
- SDK: Claude Agent SDK (uses API credits, streaming but less reliable on Windows)
"""

import asyncio
import json
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any

from pydantic import BaseModel

from .models import HarnessConfig, SessionState, Feature, SessionMode


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
    # New: capture raw output for debugging
    raw_output: Optional[str] = None
    raw_error: Optional[str] = None


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
        """
        if self.config.session_mode == SessionMode.CLI:
            return await self._run_cli_session(prompt, on_message)
        else:
            return await self._run_sdk_session(prompt, on_message)

    async def _run_cli_session(
        self,
        prompt: str,
        on_message: Optional[Callable[[Any], None]] = None
    ) -> SessionResult:
        """Run session using direct CLI invocation.

        Uses the user's Claude subscription, not API credits.
        More reliable on Windows than the SDK.
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

        # Build the claude command
        cmd = [
            claude_path,
            "-p", prompt,  # Non-interactive mode with prompt
            "--model", self.config.model,
            "--max-turns", str(self.config.cli_max_turns),
            "--dangerously-skip-permissions",  # Allow all tools for autonomous operation
        ]

        print(f"\n[CLI] Starting session with model: {self.config.model}")
        print(f"[CLI] Working directory: {self.project_path}")
        print(f"[CLI] Max turns: {self.config.cli_max_turns}")
        print(f"[CLI] Using executable: {claude_path}")
        print(f"[CLI] Prompt length: {len(prompt)} chars")
        print(f"[CLI] Command: {cmd[0]} {' '.join(cmd[1:3])}... (prompt truncated)")

        try:
            # Write prompt to a temp file to avoid shell escaping issues on Windows
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

            # Run claude CLI - use subprocess_exec directly (works with .cmd on Windows too)
            process = await asyncio.create_subprocess_exec(
                *cmd_stdin,
                cwd=str(self.project_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Send prompt via stdin and wait for completion
            stdout, stderr = await process.communicate(input=prompt.encode('utf-8'))

            # Clean up temp file
            try:
                prompt_file.unlink()
            except:
                pass

            stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
            stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ""

            # Store raw output for debugging
            result.raw_output = stdout_text
            result.raw_error = stderr_text

            # Debug: Show what we got back
            print(f"\n[CLI DEBUG] Return code: {process.returncode}")
            print(f"[CLI DEBUG] Stdout length: {len(stdout_text)} chars")
            print(f"[CLI DEBUG] Stderr length: {len(stderr_text)} chars")
            if stderr_text:
                print(f"[CLI DEBUG] Stderr: {stderr_text[:500]}")
            if not stdout_text and not stderr_text:
                print(f"[CLI DEBUG] No output received from CLI!")

            # Print output
            if stdout_text:
                print(f"\n[CLI OUTPUT]\n{stdout_text}")

            # Check for errors
            if process.returncode != 0:
                # Check for known error patterns
                error_text = stderr_text or stdout_text

                if "credit balance" in error_text.lower():
                    result.error_message = f"API Credit Error: {error_text.strip()}"
                    print(f"\n[ERROR] API credits issue: {error_text}")
                elif "rate limit" in error_text.lower():
                    result.error_message = f"Rate Limited: {error_text.strip()}"
                    print(f"\n[ERROR] Rate limited: {error_text}")
                elif "authentication" in error_text.lower() or "unauthorized" in error_text.lower():
                    result.error_message = f"Auth Error: {error_text.strip()}"
                    print(f"\n[ERROR] Authentication issue: {error_text}")
                else:
                    result.error_message = f"CLI exited with code {process.returncode}: {error_text.strip()}"
                    print(f"\n[ERROR] CLI failed (code {process.returncode})")
                    if stderr_text:
                        print(f"[STDERR] {stderr_text}")

                result.success = False
            else:
                result.success = True
                result.summary = "Session completed successfully via CLI"
                print(f"\n[CLI] Session completed successfully")

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
                    total_tokens = input_tokens + output_tokens
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

            # Always log the full error for visibility
            print(f"\n[SDK ERROR] Exception during session:")
            print(f"[SDK ERROR] {error_str}")

            # Check for specific error patterns and display clearly
            error_lower = error_str.lower()
            if "credit balance" in error_lower:
                print(f"\n{'='*60}")
                print("[BILLING ERROR] Credit balance is too low!")
                print("The SDK uses Anthropic API credits, NOT your Claude subscription.")
                print("Options:")
                print("  1. Add credits at console.anthropic.com")
                print("  2. Use CLI mode instead (uses your subscription)")
                print(f"{'='*60}\n")
                result.error_message = "API Credit Error: Credit balance is too low. SDK uses API credits, not Claude subscription."
            elif "rate limit" in error_lower or "429" in error_str:
                print(f"\n[BILLING ERROR] Rate limited - too many requests")
                result.error_message = f"Rate Limited: {error_str}"
            elif "unauthorized" in error_lower or "401" in error_str or "authentication" in error_lower:
                print(f"\n[AUTH ERROR] Authentication failed")
                result.error_message = f"Auth Error: {error_str}"
            elif "exit code 1" in error_lower or "exit code: 1" in error_lower:
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
