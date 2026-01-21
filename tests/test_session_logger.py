"""Tests for SessionLogger class."""

import json
import pytest
from datetime import datetime
from pathlib import Path

from autonomous_dev_agent.session_logger import (
    SessionLogger,
    read_session_log,
    stream_session_log,
    get_session_summary
)
from autonomous_dev_agent.workspace import WorkspaceManager
from autonomous_dev_agent.models import LogEntryType


class TestSessionLogger:
    """Tests for SessionLogger."""

    def test_creates_log_file_on_session_start(self, tmp_path: Path):
        """Test that log file is created on session start."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session_001",
            agent_type="coding",
            feature_id="user-auth",
            model="claude-sonnet-4-20250514"
        )
        logger.log_session_start()

        log_file = workspace.get_session_log_path("test_session_001")
        assert log_file.exists()

        # Verify content
        entries = read_session_log(log_file)
        assert len(entries) == 1
        assert entries[0]["type"] == LogEntryType.SESSION_START.value
        assert entries[0]["session_id"] == "test_session_001"

        logger.close()

    def test_logs_prompt(self, tmp_path: Path):
        """Test logging a prompt."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding"
        )
        logger.log_session_start()
        logger.log_prompt(
            prompt_name="coding",
            prompt_text="Implement the feature...",
            variables={"feature_id": "auth"}
        )

        log_file = workspace.get_session_log_path("test_session")
        entries = read_session_log(log_file)

        assert len(entries) == 2
        prompt_entry = entries[1]
        assert prompt_entry["type"] == LogEntryType.PROMPT.value
        assert prompt_entry["prompt_name"] == "coding"
        assert prompt_entry["prompt_text"] == "Implement the feature..."
        assert prompt_entry["variables"]["feature_id"] == "auth"

        logger.close()

    def test_logs_assistant_messages(self, tmp_path: Path):
        """Test logging assistant messages."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding"
        )
        logger.log_session_start()
        logger.log_assistant(
            content="I'll start by reading the file...",
            tool_calls=[{"tool": "Read", "input": {"file_path": "/src/main.py"}}]
        )

        entries = read_session_log(workspace.get_session_log_path("test_session"))

        assistant_entry = entries[1]
        assert assistant_entry["type"] == LogEntryType.ASSISTANT.value
        assert assistant_entry["turn"] == 1
        assert assistant_entry["content"] == "I'll start by reading the file..."
        assert len(assistant_entry["tool_calls"]) == 1

        logger.close()

    def test_logs_tool_results(self, tmp_path: Path):
        """Test logging tool results."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding"
        )
        logger.log_session_start()
        logger.log_assistant(content="Reading file...")
        logger.log_tool_result(
            tool_call_id="tc_001",
            tool="Read",
            input_data={"file_path": "/src/main.py"},
            output="def main():\n    pass",
            duration_ms=50,
            file_changed=None
        )

        entries = read_session_log(workspace.get_session_log_path("test_session"))

        tool_entry = entries[2]
        assert tool_entry["type"] == LogEntryType.TOOL_RESULT.value
        assert tool_entry["tool"] == "Read"
        assert tool_entry["duration_ms"] == 50
        assert "def main()" in tool_entry["output"]

        logger.close()

    def test_tracks_files_changed(self, tmp_path: Path):
        """Test that files changed are tracked."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding"
        )
        logger.log_session_start()
        logger.log_assistant(content="Editing file...")
        logger.log_tool_result(
            tool_call_id="tc_001",
            tool="Edit",
            input_data={"file_path": "/src/main.py"},
            output="File edited",
            file_changed="/src/main.py"
        )
        logger.log_tool_result(
            tool_call_id="tc_002",
            tool="Write",
            input_data={"file_path": "/src/utils.py"},
            output="File written",
            file_changed="/src/utils.py"
        )

        assert len(logger.files_changed) == 2
        assert "/src/main.py" in logger.files_changed
        assert "/src/utils.py" in logger.files_changed

        logger.close()

    def test_logs_context_updates(self, tmp_path: Path):
        """Test logging context/usage updates."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding"
        )
        logger.log_session_start()
        logger.log_context_update(
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=200,
            cache_write_tokens=100,
        )

        entries = read_session_log(workspace.get_session_log_path("test_session"))

        context_entry = entries[1]
        assert context_entry["type"] == LogEntryType.CONTEXT_UPDATE.value
        assert context_entry["total_input_tokens"] == 1000
        assert context_entry["total_output_tokens"] == 500
        assert context_entry["total_tokens"] == 1500

        logger.close()

    def test_logs_errors(self, tmp_path: Path):
        """Test logging errors."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding"
        )
        logger.log_session_start()
        logger.log_error(
            category="rate_limit",
            message="Too many requests",
            raw_error="429 Too Many Requests",
            recoverable=True
        )

        entries = read_session_log(workspace.get_session_log_path("test_session"))

        error_entry = entries[1]
        assert error_entry["type"] == LogEntryType.ERROR.value
        assert error_entry["category"] == "rate_limit"
        assert error_entry["message"] == "Too many requests"
        assert error_entry["recoverable"] is True

        logger.close()

    def test_logs_session_end(self, tmp_path: Path):
        """Test logging session end."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding",
            feature_id="auth"
        )
        logger.log_session_start()
        logger.log_assistant(content="Done!")
        logger.log_context_update(input_tokens=1000, output_tokens=500)

        index_entry = logger.log_session_end(
            outcome="success",
            reason="Feature completed",
            commit_hash="abc123"
        )

        entries = read_session_log(workspace.get_session_log_path("test_session"))

        end_entry = entries[-1]
        assert end_entry["type"] == LogEntryType.SESSION_END.value
        assert end_entry["outcome"] == "success"
        assert end_entry["reason"] == "Feature completed"
        assert end_entry["turns"] == 1

        # Verify index entry
        assert index_entry.session_id == "test_session"
        assert index_entry.outcome == "success"
        assert index_entry.turns == 1

    def test_updates_session_index(self, tmp_path: Path):
        """Test that session end updates the session index."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding",
            feature_id="auth"
        )
        logger.log_session_start()
        logger.log_session_end(outcome="success")

        # Verify index was updated
        index = workspace.get_session_index()
        assert index.total_sessions == 1
        assert index.sessions[0].session_id == "test_session"
        assert index.sessions[0].outcome == "success"

    def test_sets_and_clears_current_session(self, tmp_path: Path):
        """Test that current session is set and cleared."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        logger = SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding"
        )
        logger.log_session_start()

        # Should be set as current
        assert workspace.get_current_session_id() == "test_session"

        logger.log_session_end(outcome="success")

        # Should be cleared
        assert workspace.get_current_session_id() is None

    def test_context_manager(self, tmp_path: Path):
        """Test using SessionLogger as context manager."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        with SessionLogger(
            workspace=workspace,
            session_id="test_session",
            agent_type="coding"
        ) as logger:
            logger.log_session_start()
            logger.log_assistant(content="Test")

        # File should be closed
        log_file = workspace.get_session_log_path("test_session")
        entries = read_session_log(log_file)
        assert len(entries) == 2


class TestReadSessionLog:
    """Tests for read_session_log function."""

    def test_reads_all_entries(self, tmp_path: Path):
        """Test reading all entries from a log file."""
        log_file = tmp_path / "test.jsonl"
        log_file.write_text(
            '{"type": "session_start", "session_id": "s1"}\n'
            '{"type": "assistant", "content": "Hello"}\n'
            '{"type": "session_end", "outcome": "success"}\n'
        )

        entries = read_session_log(log_file)

        assert len(entries) == 3
        assert entries[0]["type"] == "session_start"
        assert entries[1]["type"] == "assistant"
        assert entries[2]["type"] == "session_end"

    def test_handles_missing_file(self, tmp_path: Path):
        """Test reading from non-existent file."""
        entries = read_session_log(tmp_path / "nonexistent.jsonl")
        assert entries == []

    def test_skips_invalid_json_lines(self, tmp_path: Path):
        """Test that invalid JSON lines are skipped."""
        log_file = tmp_path / "test.jsonl"
        log_file.write_text(
            '{"type": "session_start"}\n'
            'this is not json\n'
            '{"type": "session_end"}\n'
        )

        entries = read_session_log(log_file)

        assert len(entries) == 2


class TestStreamSessionLog:
    """Tests for stream_session_log function."""

    def test_streams_entries(self, tmp_path: Path):
        """Test streaming entries from a log file."""
        log_file = tmp_path / "test.jsonl"
        log_file.write_text(
            '{"type": "session_start"}\n'
            '{"type": "assistant"}\n'
        )

        entries = list(stream_session_log(log_file, follow=False))

        assert len(entries) == 2

    def test_handles_missing_file(self, tmp_path: Path):
        """Test streaming from non-existent file."""
        entries = list(stream_session_log(tmp_path / "nonexistent.jsonl"))
        assert entries == []


class TestGetSessionSummary:
    """Tests for get_session_summary function."""

    def test_extracts_summary(self, tmp_path: Path):
        """Test extracting session summary."""
        log_file = tmp_path / "test.jsonl"
        log_file.write_text(
            '{"type": "session_start", "timestamp": "2024-01-15T10:00:00", "session_id": "s1", "agent_type": "coding", "feature_id": "auth", "model": "claude-sonnet"}\n'
            '{"type": "assistant", "turn": 1, "content": "Working..."}\n'
            '{"type": "assistant", "turn": 2, "content": "Done!"}\n'
            '{"type": "context_update", "total_tokens": 5000}\n'
            '{"type": "error", "category": "transient", "message": "Network error"}\n'
            '{"type": "session_end", "timestamp": "2024-01-15T10:30:00", "outcome": "success", "files_changed": ["/src/auth.py"]}\n'
        )

        summary = get_session_summary(log_file)

        assert summary["session_id"] == "s1"
        assert summary["agent_type"] == "coding"
        assert summary["feature_id"] == "auth"
        assert summary["model"] == "claude-sonnet"
        assert summary["turns"] == 2
        assert summary["total_tokens"] == 5000
        assert summary["outcome"] == "success"
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["category"] == "transient"
        assert "/src/auth.py" in summary["files_changed"]

    def test_handles_missing_file(self, tmp_path: Path):
        """Test summary of non-existent file."""
        summary = get_session_summary(tmp_path / "nonexistent.jsonl")
        assert summary is None

    def test_handles_empty_file(self, tmp_path: Path):
        """Test summary of empty file."""
        log_file = tmp_path / "test.jsonl"
        log_file.write_text("")

        summary = get_session_summary(log_file)
        assert summary is None
