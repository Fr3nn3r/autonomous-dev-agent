"""Session logging for JSONL-based observability.

Provides real-time JSONL logging of session events including:
- Session start/end
- Prompts sent
- Assistant messages
- Tool calls and results
- Context updates
- Errors

Logs are written with immediate flush (os.fsync) for real-time streaming.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from .models import LogEntryType, SessionIndexEntry
from .workspace import WorkspaceManager


class SessionLogger:
    """JSONL session logger with real-time flush.

    Writes session events to JSONL files for debugging and analysis.
    Each line is a complete JSON object with timestamp and type.

    Example output:
        {"type": "session_start", "timestamp": "...", "session_id": "..."}
        {"type": "prompt", "timestamp": "...", "prompt_name": "coding", ...}
        {"type": "assistant", "timestamp": "...", "turn": 1, "content": "..."}
        {"type": "tool_result", "timestamp": "...", "tool": "Read", ...}
        {"type": "session_end", "timestamp": "...", "outcome": "success", ...}

    Output truncation:
        By default, tool outputs are truncated at 50KB to prevent log bloat.
        Set output_truncation_limit=0 to disable truncation entirely.
    """

    # Default truncation limit (50KB)
    DEFAULT_TRUNCATION_LIMIT = 50000

    def __init__(
        self,
        workspace: WorkspaceManager,
        session_id: str,
        agent_type: str = "coding",
        feature_id: Optional[str] = None,
        feature_name: Optional[str] = None,
        model: str = "",
        config: Optional[dict] = None,
        output_truncation_limit: int = DEFAULT_TRUNCATION_LIMIT
    ):
        """Initialize session logger.

        Args:
            workspace: WorkspaceManager instance
            session_id: Unique session identifier
            agent_type: Type of agent (initializer or coding)
            feature_id: Feature being worked on
            feature_name: Human-readable feature name
            model: Model being used
            config: Session configuration dict
            output_truncation_limit: Max chars for tool output (0 to disable truncation)
        """
        self.workspace = workspace
        self.session_id = session_id
        self.agent_type = agent_type
        self.feature_id = feature_id
        self.feature_name = feature_name
        self.model = model
        self.config = config or {}
        self.output_truncation_limit = output_truncation_limit

        # Ensure workspace structure exists
        workspace.ensure_structure()

        # Log file path
        self.log_file = workspace.get_session_log_path(session_id)

        # Tracking
        self._turn = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cache_read = 0
        self._total_cache_write = 0
        self._files_changed: list[str] = []
        self._started_at = datetime.now()
        self._file_handle: Optional[Any] = None

    def _write_entry(self, entry: dict) -> None:
        """Write a log entry with immediate flush.

        Args:
            entry: Dict to write as JSON line
        """
        # Add timestamp if not present
        if "timestamp" not in entry:
            entry["timestamp"] = datetime.now().isoformat()

        # Open file in append mode if not already open
        if self._file_handle is None:
            self._file_handle = open(self.log_file, "a", encoding="utf-8")

        # Write and flush
        self._file_handle.write(json.dumps(entry, default=str) + "\n")
        self._file_handle.flush()

        # Force write to disk for real-time streaming
        try:
            os.fsync(self._file_handle.fileno())
        except (OSError, AttributeError):
            pass  # Some systems don't support fsync

    def log_session_start(self) -> None:
        """Log session start event."""
        self._write_entry({
            "type": LogEntryType.SESSION_START.value,
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "feature_id": self.feature_id,
            "feature_name": self.feature_name,
            "model": self.model,
            "config": self.config
        })

        # Set as current session in workspace
        self.workspace.set_current_session(self.session_id)

    def log_prompt(
        self,
        prompt_name: str,
        prompt_text: str,
        variables: Optional[dict] = None
    ) -> None:
        """Log a prompt sent to the agent.

        Args:
            prompt_name: Name of the prompt template
            prompt_text: Full prompt text
            variables: Variables used in the prompt template
        """
        self._write_entry({
            "type": LogEntryType.PROMPT.value,
            "prompt_name": prompt_name,
            "prompt_length": len(prompt_text),
            "prompt_text": prompt_text,
            "variables": variables or {}
        })

    def log_assistant(
        self,
        content: str,
        tool_calls: Optional[list[dict]] = None,
        thinking: Optional[str] = None
    ) -> None:
        """Log an assistant message.

        Args:
            content: Message content
            tool_calls: List of tool calls made
            thinking: Thinking/reasoning content (if available)
        """
        self._turn += 1
        self._write_entry({
            "type": LogEntryType.ASSISTANT.value,
            "turn": self._turn,
            "content": content,
            "thinking": thinking,
            "tool_calls": tool_calls or []
        })

    def log_tool_result(
        self,
        tool_call_id: str,
        tool: str,
        input_data: dict,
        output: str,
        duration_ms: Optional[int] = None,
        truncated: bool = False,
        file_changed: Optional[str] = None
    ) -> None:
        """Log a tool result.

        Args:
            tool_call_id: ID of the tool call
            tool: Tool name
            input_data: Tool input parameters
            output: Tool output
            duration_ms: Execution duration in milliseconds
            truncated: Whether output was truncated
            file_changed: File path if a file was modified
        """
        # Apply truncation if configured
        truncation_limit = self.output_truncation_limit
        should_truncate = truncation_limit > 0 and len(output) > truncation_limit
        output_to_log = output[:truncation_limit] if should_truncate else output

        entry = {
            "type": LogEntryType.TOOL_RESULT.value,
            "turn": self._turn,
            "tool_call_id": tool_call_id,
            "tool": tool,
            "input": input_data,
            "output": output_to_log,
            "output_length": len(output),
            "duration_ms": duration_ms,
            "truncated": truncated or should_truncate
        }

        if file_changed:
            entry["file_changed"] = file_changed
            if file_changed not in self._files_changed:
                self._files_changed.append(file_changed)

        self._write_entry(entry)

    def log_context_update(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        """Log a context/usage update.

        Args:
            input_tokens: Input tokens for this turn
            output_tokens: Output tokens for this turn
            cache_read_tokens: Cache read tokens
            cache_write_tokens: Cache write tokens
        """
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_cache_read += cache_read_tokens
        self._total_cache_write += cache_write_tokens

        total_tokens = self._total_input_tokens + self._total_output_tokens

        # Estimate context percentage (assuming 200k context window)
        context_percent = (total_tokens / 200000) * 100

        self._write_entry({
            "type": LogEntryType.CONTEXT_UPDATE.value,
            "turn": self._turn,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_write_tokens": cache_write_tokens,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": total_tokens,
            "context_percent": round(context_percent, 2),
        })

    def log_error(
        self,
        category: str,
        message: str,
        raw_error: Optional[str] = None,
        recoverable: bool = True
    ) -> None:
        """Log an error event.

        Args:
            category: Error category (rate_limit, auth, billing, etc.)
            message: Error message
            raw_error: Raw error string/traceback
            recoverable: Whether the error is recoverable
        """
        self._write_entry({
            "type": LogEntryType.ERROR.value,
            "turn": self._turn,
            "category": category,
            "message": message,
            "raw_error": raw_error,
            "recoverable": recoverable
        })

    def log_session_end(
        self,
        outcome: str,
        reason: Optional[str] = None,
        handoff_notes: Optional[str] = None,
        commit_hash: Optional[str] = None
    ) -> SessionIndexEntry:
        """Log session end and update the index.

        Args:
            outcome: Session outcome (success, failure, handoff, timeout)
            reason: Reason for ending
            handoff_notes: Notes for the next session (if handoff)
            commit_hash: Git commit hash if committed

        Returns:
            SessionIndexEntry for this session
        """
        ended_at = datetime.now()
        duration_seconds = (ended_at - self._started_at).total_seconds()

        self._write_entry({
            "type": LogEntryType.SESSION_END.value,
            "session_id": self.session_id,
            "outcome": outcome,
            "reason": reason,
            "duration_seconds": round(duration_seconds, 2),
            "turns": self._turn,
            "tokens": {
                "input": self._total_input_tokens,
                "output": self._total_output_tokens,
                "cache_read": self._total_cache_read,
                "cache_write": self._total_cache_write
            },
            "files_changed": self._files_changed,
            "commit_hash": commit_hash,
            "handoff_notes": handoff_notes
        })

        # Close file handle
        self.close()

        # Get file size
        file_size = self.log_file.stat().st_size if self.log_file.exists() else 0

        # Create and update index entry
        entry = SessionIndexEntry(
            session_id=self.session_id,
            file=f"sessions/{self.session_id}.jsonl",
            agent_type=self.agent_type,
            feature_id=self.feature_id,
            started_at=self._started_at,
            ended_at=ended_at,
            outcome=outcome,
            turns=self._turn,
            tokens_total=self._total_input_tokens + self._total_output_tokens,
            size_bytes=file_size
        )

        self.workspace.update_session_index(entry)
        self.workspace.clear_current_session()

        return entry

    def close(self) -> None:
        """Close the log file handle."""
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None

    def __enter__(self) -> "SessionLogger":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    @property
    def turn(self) -> int:
        """Get current turn number."""
        return self._turn

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        return self._total_input_tokens + self._total_output_tokens

    @property
    def files_changed(self) -> list[str]:
        """Get list of files changed."""
        return self._files_changed.copy()


def read_session_log(log_path: Path) -> list[dict]:
    """Read all entries from a session log file.

    Args:
        log_path: Path to the JSONL log file

    Returns:
        List of log entry dicts
    """
    entries = []
    if not log_path.exists():
        return entries

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return entries


def stream_session_log(log_path: Path, follow: bool = False):
    """Stream entries from a session log file.

    Args:
        log_path: Path to the JSONL log file
        follow: If True, continue reading as new entries are added

    Yields:
        Log entry dicts
    """
    import time

    if not log_path.exists():
        return

    with open(log_path, "r", encoding="utf-8") as f:
        while True:
            line = f.readline()

            if line:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        pass
            elif follow:
                # No new data, wait briefly
                time.sleep(0.1)
            else:
                # Not following, done reading
                break


def get_session_summary(log_path: Path) -> Optional[dict]:
    """Get a summary of a session from its log file.

    Args:
        log_path: Path to the JSONL log file

    Returns:
        Summary dict or None if not found
    """
    entries = read_session_log(log_path)
    if not entries:
        return None

    summary = {
        "session_id": None,
        "agent_type": None,
        "feature_id": None,
        "model": None,
        "started_at": None,
        "ended_at": None,
        "outcome": None,
        "turns": 0,
        "total_tokens": 0,
        "files_changed": [],
        "errors": []
    }

    for entry in entries:
        entry_type = entry.get("type")

        if entry_type == LogEntryType.SESSION_START.value:
            summary["session_id"] = entry.get("session_id")
            summary["agent_type"] = entry.get("agent_type")
            summary["feature_id"] = entry.get("feature_id")
            summary["model"] = entry.get("model")
            summary["started_at"] = entry.get("timestamp")

        elif entry_type == LogEntryType.ASSISTANT.value:
            summary["turns"] = max(summary["turns"], entry.get("turn", 0))

        elif entry_type == LogEntryType.CONTEXT_UPDATE.value:
            summary["total_tokens"] = entry.get("total_tokens", 0)

        elif entry_type == LogEntryType.ERROR.value:
            summary["errors"].append({
                "category": entry.get("category"),
                "message": entry.get("message")
            })

        elif entry_type == LogEntryType.SESSION_END.value:
            summary["ended_at"] = entry.get("timestamp")
            summary["outcome"] = entry.get("outcome")
            summary["files_changed"] = entry.get("files_changed", [])

    return summary
