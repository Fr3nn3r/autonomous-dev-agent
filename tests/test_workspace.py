"""Tests for WorkspaceManager class."""

import json
import pytest
from datetime import datetime
from pathlib import Path

from autonomous_dev_agent.workspace import WorkspaceManager
from autonomous_dev_agent.models import SessionIndexEntry, SessionIndex, ProjectContext


class TestWorkspaceManager:
    """Tests for WorkspaceManager."""

    def test_ensure_structure_creates_directories(self, tmp_path: Path):
        """Test that ensure_structure creates the .ada/ directory structure."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        assert workspace.ada_dir.exists()
        assert workspace.logs_dir.exists()
        assert workspace.sessions_dir.exists()
        assert workspace.state_dir.exists()
        assert workspace.prompts_dir.exists()
        assert workspace.hooks_dir.exists()
        assert workspace.baselines_dir.exists()
        assert workspace.index_file.exists()

    def test_exists_returns_false_for_new_project(self, tmp_path: Path):
        """Test that exists() returns False for new project."""
        workspace = WorkspaceManager(tmp_path)
        assert not workspace.exists()

    def test_exists_returns_true_after_ensure_structure(self, tmp_path: Path):
        """Test that exists() returns True after structure is created."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()
        assert workspace.exists()

    def test_create_project_context(self, tmp_path: Path):
        """Test creating and saving project context."""
        workspace = WorkspaceManager(tmp_path)

        context = workspace.create_project_context(
            name="Test Project",
            description="A test project",
            created_by="test"
        )

        assert context.name == "Test Project"
        assert context.description == "A test project"
        assert context.created_by == "test"
        assert workspace.project_file.exists()

        # Reload and verify
        loaded = workspace.get_project_context()
        assert loaded is not None
        assert loaded.name == "Test Project"
        assert loaded.description == "A test project"

    def test_get_project_context_returns_none_when_missing(self, tmp_path: Path):
        """Test that get_project_context returns None when file doesn't exist."""
        workspace = WorkspaceManager(tmp_path)
        assert workspace.get_project_context() is None

    def test_create_project_context_with_init_session(self, tmp_path: Path):
        """Test creating project context with init_session info."""
        workspace = WorkspaceManager(tmp_path)

        init_session_info = {
            "spec_file": "/path/to/spec.md",
            "model": "claude-sonnet-4-20250514",
            "feature_count": 15,
            "outcome": "success",
            "generated_at": "2024-01-15T10:30:00"
        }

        context = workspace.create_project_context(
            name="Test Project",
            description="A test project",
            created_by="test",
            init_session=init_session_info
        )

        assert context.init_session is not None
        assert context.init_session["spec_file"] == "/path/to/spec.md"
        assert context.init_session["feature_count"] == 15

        # Reload and verify
        loaded = workspace.get_project_context()
        assert loaded.init_session is not None
        assert loaded.init_session["model"] == "claude-sonnet-4-20250514"

    def test_session_index_operations(self, tmp_path: Path):
        """Test session index CRUD operations."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        # Create and add a session entry
        entry = SessionIndexEntry(
            session_id="20240115_001_coding_feature-1",
            file="sessions/20240115_001_coding_feature-1.jsonl",
            agent_type="coding",
            feature_id="feature-1",
            started_at=datetime.now(),
            outcome="success",
            turns=5,
            tokens_total=10000,
            size_bytes=1024
        )

        workspace.update_session_index(entry)

        # Load and verify
        index = workspace.get_session_index()
        assert index.total_sessions == 1
        assert index.total_size_bytes == 1024
        assert len(index.sessions) == 1
        assert index.sessions[0].session_id == "20240115_001_coding_feature-1"

    def test_get_next_session_id(self, tmp_path: Path):
        """Test session ID generation."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        # First session
        session_id = workspace.get_next_session_id(
            agent_type="coding",
            feature_id="user-auth"
        )

        today = datetime.now().strftime("%Y%m%d")
        assert session_id.startswith(today)
        assert "_001_" in session_id
        assert "coding" in session_id
        assert "user-auth" in session_id

    def test_get_next_session_id_increments(self, tmp_path: Path):
        """Test that session ID sequence increments."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        # Add a session to the index
        today = datetime.now().strftime("%Y%m%d")
        entry = SessionIndexEntry(
            session_id=f"{today}_001_coding_test",
            file=f"sessions/{today}_001_coding_test.jsonl",
            agent_type="coding",
            started_at=datetime.now()
        )
        workspace.update_session_index(entry)

        # Next session should be 002
        session_id = workspace.get_next_session_id(agent_type="coding")
        assert "_002_" in session_id

    def test_get_session_log_path(self, tmp_path: Path):
        """Test session log path generation."""
        workspace = WorkspaceManager(tmp_path)

        path = workspace.get_session_log_path("20240115_001_coding")

        assert path.name == "20240115_001_coding.jsonl"
        assert path.parent.name == "sessions"

    def test_current_session_management(self, tmp_path: Path):
        """Test current session get/set/clear operations."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        # Initially no current session
        assert workspace.get_current_session_id() is None

        # Set current session
        workspace.set_current_session("test-session-123")
        assert workspace.get_current_session_id() == "test-session-123"

        # Clear current session
        workspace.clear_current_session()
        assert workspace.get_current_session_id() is None

    def test_get_logs_size_bytes(self, tmp_path: Path):
        """Test log size calculation."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        # Initially 0
        assert workspace.get_logs_size_bytes() == 0

        # Create a log file
        log_file = workspace.sessions_dir / "test.jsonl"
        log_file.write_text('{"test": "data"}\n' * 100)

        # Should reflect file size
        assert workspace.get_logs_size_bytes() > 0

    def test_should_rotate_false_when_small(self, tmp_path: Path):
        """Test that should_rotate returns False for small logs."""
        workspace = WorkspaceManager(tmp_path)
        workspace.ensure_structure()

        # Create a small log file
        log_file = workspace.sessions_dir / "test.jsonl"
        log_file.write_text('{"test": "data"}\n')

        assert not workspace.should_rotate()

    def test_legacy_file_detection(self, tmp_path: Path):
        """Test detection of legacy state files."""
        workspace = WorkspaceManager(tmp_path)

        # Create legacy files
        (tmp_path / ".ada_session_state.json").write_text("{}")
        (tmp_path / ".ada_session_history.json").write_text("[]")
        (tmp_path / ".ada_alerts.json").write_text("[]")

        assert workspace.get_legacy_state_file() is not None
        assert workspace.get_legacy_history_file() is not None
        assert workspace.get_legacy_alerts_file() is not None

    def test_migrate_legacy_files(self, tmp_path: Path):
        """Test migration of legacy files to new locations."""
        workspace = WorkspaceManager(tmp_path)

        # Create legacy files with content
        (tmp_path / ".ada_session_state.json").write_text('{"test": "state"}')
        (tmp_path / ".ada_session_history.json").write_text('[{"test": "history"}]')
        (tmp_path / ".ada_alerts.json").write_text('[{"test": "alert"}]')

        # Run migration
        results = workspace.migrate_legacy_files()

        # Verify migration
        assert results.get("session_state") is True
        assert results.get("session_history") is True
        assert results.get("alerts") is True

        # Verify new locations
        assert workspace.session_state_file.exists()
        assert workspace.session_history_file.exists()
        assert workspace.alerts_file.exists()

        # Verify legacy files are gone
        assert not (tmp_path / ".ada_session_state.json").exists()
        assert not (tmp_path / ".ada_session_history.json").exists()
        assert not (tmp_path / ".ada_alerts.json").exists()

    def test_update_gitignore(self, tmp_path: Path):
        """Test .gitignore update."""
        workspace = WorkspaceManager(tmp_path)

        # First update should return True
        assert workspace.update_gitignore() is True

        gitignore = tmp_path / ".gitignore"
        content = gitignore.read_text()
        assert ".ada/logs/" in content
        assert ".ada/state/" in content

        # Second update should return False (already has patterns)
        assert workspace.update_gitignore() is False

    def test_update_gitignore_appends_to_existing(self, tmp_path: Path):
        """Test that .gitignore preserves existing content."""
        workspace = WorkspaceManager(tmp_path)

        # Create existing .gitignore
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n.env\n")

        workspace.update_gitignore()

        content = gitignore.read_text()
        assert "node_modules/" in content
        assert ".env" in content
        assert ".ada/logs/" in content

    def test_get_workspace_stats(self, tmp_path: Path):
        """Test workspace statistics."""
        workspace = WorkspaceManager(tmp_path)
        workspace.create_project_context(name="Test", description="Test project")

        # Add some sessions
        for i in range(3):
            entry = SessionIndexEntry(
                session_id=f"session_{i}",
                file=f"sessions/session_{i}.jsonl",
                agent_type="coding",
                started_at=datetime.now(),
                ended_at=datetime.now(),
                outcome="success" if i < 2 else "failure",
                tokens_total=1000 * (i + 1),
                size_bytes=100 * (i + 1)
            )
            workspace.update_session_index(entry)

        stats = workspace.get_workspace_stats()

        assert stats["project_name"] == "Test"
        assert stats["project_description"] == "Test project"
        assert stats["total_sessions"] == 3
        assert stats["total_tokens"] == 6000  # 1000 + 2000 + 3000
        assert stats["outcomes"]["success"] == 2
        assert stats["outcomes"]["failure"] == 1

    def test_get_workspace_stats_with_init_session(self, tmp_path: Path):
        """Test workspace statistics include init_session."""
        workspace = WorkspaceManager(tmp_path)

        init_session_info = {
            "spec_file": "/path/to/spec.md",
            "model": "claude-sonnet-4-20250514",
            "feature_count": 10,
            "outcome": "success",
            "generated_at": "2024-01-15T10:30:00"
        }

        workspace.create_project_context(
            name="Test",
            description="Test project",
            init_session=init_session_info
        )

        stats = workspace.get_workspace_stats()

        assert stats["init_session"] is not None
        assert stats["init_session"]["spec_file"] == "/path/to/spec.md"
        assert stats["init_session"]["feature_count"] == 10


class TestSessionIndex:
    """Tests for SessionIndex model methods."""

    def test_add_session(self):
        """Test adding a session to the index."""
        index = SessionIndex()
        entry = SessionIndexEntry(
            session_id="test-1",
            file="sessions/test-1.jsonl",
            agent_type="coding",
            size_bytes=1000
        )

        index.add_session(entry)

        assert index.total_sessions == 1
        assert index.total_size_bytes == 1000
        assert len(index.sessions) == 1

    def test_get_session(self):
        """Test getting a session by ID."""
        index = SessionIndex()
        entry = SessionIndexEntry(
            session_id="test-1",
            file="sessions/test-1.jsonl",
            agent_type="coding"
        )
        index.add_session(entry)

        found = index.get_session("test-1")
        assert found is not None
        assert found.session_id == "test-1"

        not_found = index.get_session("nonexistent")
        assert not_found is None

    def test_update_session(self):
        """Test updating a session entry."""
        index = SessionIndex()
        entry = SessionIndexEntry(
            session_id="test-1",
            file="sessions/test-1.jsonl",
            agent_type="coding",
            outcome=None,
            size_bytes=1000
        )
        index.add_session(entry)

        # Update the session
        success = index.update_session("test-1", outcome="success", size_bytes=2000)

        assert success is True
        updated = index.get_session("test-1")
        assert updated.outcome == "success"
        assert updated.size_bytes == 2000
        assert index.total_size_bytes == 2000

    def test_get_recent_sessions(self):
        """Test getting recent sessions sorted by date."""
        index = SessionIndex()

        # Add sessions with different times
        for i in range(5):
            entry = SessionIndexEntry(
                session_id=f"test-{i}",
                file=f"sessions/test-{i}.jsonl",
                agent_type="coding",
                started_at=datetime(2024, 1, 15, 10, i)  # Different minutes
            )
            index.add_session(entry)

        recent = index.get_recent_sessions(count=3)

        assert len(recent) == 3
        # Should be in reverse chronological order
        assert recent[0].session_id == "test-4"
        assert recent[1].session_id == "test-3"
        assert recent[2].session_id == "test-2"

    def test_get_sessions_by_feature(self):
        """Test filtering sessions by feature ID."""
        index = SessionIndex()

        index.add_session(SessionIndexEntry(
            session_id="s1", file="s1.jsonl", agent_type="coding", feature_id="auth"
        ))
        index.add_session(SessionIndexEntry(
            session_id="s2", file="s2.jsonl", agent_type="coding", feature_id="payment"
        ))
        index.add_session(SessionIndexEntry(
            session_id="s3", file="s3.jsonl", agent_type="coding", feature_id="auth"
        ))

        auth_sessions = index.get_sessions_by_feature("auth")

        assert len(auth_sessions) == 2
        assert all(s.feature_id == "auth" for s in auth_sessions)

    def test_get_sessions_by_outcome(self):
        """Test filtering sessions by outcome."""
        index = SessionIndex()

        index.add_session(SessionIndexEntry(
            session_id="s1", file="s1.jsonl", agent_type="coding", outcome="success"
        ))
        index.add_session(SessionIndexEntry(
            session_id="s2", file="s2.jsonl", agent_type="coding", outcome="failure"
        ))
        index.add_session(SessionIndexEntry(
            session_id="s3", file="s3.jsonl", agent_type="coding", outcome="success"
        ))

        success_sessions = index.get_sessions_by_outcome("success")

        assert len(success_sessions) == 2
        assert all(s.outcome == "success" for s in success_sessions)
