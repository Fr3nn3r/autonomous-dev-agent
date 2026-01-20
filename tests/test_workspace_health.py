"""Tests for workspace health checking and repair."""

import json
import pytest
from datetime import datetime
from pathlib import Path

from autonomous_dev_agent.models import (
    HealthIssue,
    HealthIssueType,
    HealthIssueSeverity,
    HealthReport,
    LogEntryType,
    Backlog,
    Feature,
    FeatureStatus,
)
from autonomous_dev_agent.workspace import WorkspaceManager
from autonomous_dev_agent.workspace_health import WorkspaceHealthChecker, WorkspaceCleaner


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory with basic structure."""
    project_path = tmp_path / "test-project"
    project_path.mkdir()

    # Create .ada workspace structure
    workspace = WorkspaceManager(project_path)
    workspace.ensure_structure()

    # Create a basic backlog
    backlog = Backlog(
        project_name="Test Project",
        project_path=str(project_path),
        features=[
            Feature(id="test-feature", name="Test", description="Test feature"),
        ]
    )
    (project_path / "feature-list.json").write_text(backlog.model_dump_json())

    return project_path


class TestWorkspaceHealthChecker:
    """Tests for WorkspaceHealthChecker."""

    def test_healthy_workspace_returns_empty_report(self, temp_project):
        """A properly initialized workspace should be healthy."""
        checker = WorkspaceHealthChecker(temp_project)
        report = checker.check_all()

        assert report.healthy is True
        assert report.critical_count == 0
        assert report.warning_count == 0

    def test_detects_crashed_session(self, temp_project):
        """Should detect sessions with session_start but no session_end."""
        workspace = WorkspaceManager(temp_project)

        # Create a session log with only session_start
        session_id = "20240115_001_coding_test"
        log_path = workspace.get_session_log_path(session_id)
        log_path.write_text(json.dumps({
            "type": LogEntryType.SESSION_START.value,
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "agent_type": "coding",
            "feature_id": "test-feature",
        }) + "\n")

        checker = WorkspaceHealthChecker(temp_project, workspace=workspace)
        report = checker.check_all()

        assert report.healthy is False
        assert report.warning_count >= 1

        crashed_issues = [i for i in report.issues if i.type == HealthIssueType.CRASHED_SESSION]
        assert len(crashed_issues) == 1
        assert crashed_issues[0].session_id == session_id
        assert crashed_issues[0].auto_fixable is True

    def test_detects_stale_current_session(self, temp_project):
        """Should detect current.jsonl pointing to ended session."""
        workspace = WorkspaceManager(temp_project)

        # Create a session log with session_end
        session_id = "20240115_001_coding_test"
        log_path = workspace.get_session_log_path(session_id)
        log_path.write_text(
            json.dumps({"type": LogEntryType.SESSION_START.value, "session_id": session_id, "timestamp": datetime.now().isoformat()}) + "\n" +
            json.dumps({"type": LogEntryType.SESSION_END.value, "outcome": "success", "timestamp": datetime.now().isoformat()}) + "\n"
        )

        # Set it as current (which is wrong since it ended)
        workspace.set_current_session(session_id)

        checker = WorkspaceHealthChecker(temp_project, workspace=workspace)
        report = checker.check_all()

        assert report.healthy is False
        stale_issues = [i for i in report.issues if i.type == HealthIssueType.STALE_CURRENT]
        assert len(stale_issues) == 1
        assert stale_issues[0].auto_fixable is True

    def test_detects_orphan_log(self, temp_project):
        """Should detect log files not in index."""
        workspace = WorkspaceManager(temp_project)

        # Create a session log without adding to index
        session_id = "20240115_001_coding_orphan"
        log_path = workspace.get_session_log_path(session_id)
        log_path.write_text(
            json.dumps({"type": LogEntryType.SESSION_START.value, "session_id": session_id, "timestamp": datetime.now().isoformat()}) + "\n" +
            json.dumps({"type": LogEntryType.SESSION_END.value, "outcome": "success", "timestamp": datetime.now().isoformat()}) + "\n"
        )

        checker = WorkspaceHealthChecker(temp_project, workspace=workspace)
        report = checker.check_all()

        assert report.healthy is False
        orphan_issues = [i for i in report.issues if i.type == HealthIssueType.ORPHAN_LOG]
        assert len(orphan_issues) == 1
        assert orphan_issues[0].session_id == session_id
        assert orphan_issues[0].auto_fixable is True

    def test_detects_session_collision(self, temp_project):
        """Should detect sessions with same date_seq prefix."""
        workspace = WorkspaceManager(temp_project)
        from autonomous_dev_agent.models import SessionIndexEntry

        # Add two sessions with same date_seq prefix
        workspace.update_session_index(SessionIndexEntry(
            session_id="20240115_001_coding_feature1",
            file="sessions/20240115_001_coding_feature1.jsonl",
            agent_type="coding",
            started_at=datetime.now(),
        ))
        workspace.update_session_index(SessionIndexEntry(
            session_id="20240115_001_coding_feature2",
            file="sessions/20240115_001_coding_feature2.jsonl",
            agent_type="coding",
            started_at=datetime.now(),
        ))

        # Create the log files so they don't show as missing
        workspace.get_session_log_path("20240115_001_coding_feature1").write_text(
            json.dumps({"type": LogEntryType.SESSION_START.value, "timestamp": datetime.now().isoformat()}) + "\n" +
            json.dumps({"type": LogEntryType.SESSION_END.value, "outcome": "success", "timestamp": datetime.now().isoformat()}) + "\n"
        )
        workspace.get_session_log_path("20240115_001_coding_feature2").write_text(
            json.dumps({"type": LogEntryType.SESSION_START.value, "timestamp": datetime.now().isoformat()}) + "\n" +
            json.dumps({"type": LogEntryType.SESSION_END.value, "outcome": "success", "timestamp": datetime.now().isoformat()}) + "\n"
        )

        checker = WorkspaceHealthChecker(temp_project, workspace=workspace)
        report = checker.check_all()

        collision_issues = [i for i in report.issues if i.type == HealthIssueType.SESSION_COLLISION]
        assert len(collision_issues) == 1
        assert collision_issues[0].auto_fixable is False

    def test_detects_stale_feature(self, temp_project):
        """Should detect features stuck in in_progress without active session."""
        # Update backlog with in_progress feature
        backlog = Backlog(
            project_name="Test Project",
            project_path=str(temp_project),
            features=[
                Feature(
                    id="stale-feature",
                    name="Stale",
                    description="Stuck feature",
                    status=FeatureStatus.IN_PROGRESS
                ),
            ]
        )
        (temp_project / "feature-list.json").write_text(backlog.model_dump_json())

        checker = WorkspaceHealthChecker(temp_project)
        report = checker.check_all()

        stale_issues = [i for i in report.issues if i.type == HealthIssueType.STALE_FEATURE]
        assert len(stale_issues) == 1
        assert stale_issues[0].feature_id == "stale-feature"
        assert stale_issues[0].auto_fixable is False


class TestWorkspaceCleaner:
    """Tests for WorkspaceCleaner."""

    def test_fixes_crashed_session(self, temp_project):
        """Should append session_end to crashed sessions."""
        workspace = WorkspaceManager(temp_project)

        # Create a crashed session
        session_id = "20240115_001_coding_crashed"
        log_path = workspace.get_session_log_path(session_id)
        log_path.write_text(json.dumps({
            "type": LogEntryType.SESSION_START.value,
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "agent_type": "coding",
            "feature_id": "test-feature",
        }) + "\n")

        # Run check and fix
        checker = WorkspaceHealthChecker(temp_project, workspace=workspace)
        report = checker.check_all()

        cleaner = WorkspaceCleaner(temp_project, workspace=workspace)
        fixed = cleaner.fix_auto(report)

        assert len(fixed) >= 1

        # Verify session_end was added
        entries = []
        with open(log_path) as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))

        end_entries = [e for e in entries if e.get("type") == LogEntryType.SESSION_END.value]
        assert len(end_entries) == 1
        assert end_entries[0]["outcome"] == "crashed"

    def test_fixes_stale_current(self, temp_project):
        """Should delete stale current.jsonl."""
        workspace = WorkspaceManager(temp_project)

        # Create a valid session
        session_id = "20240115_001_coding_ended"
        log_path = workspace.get_session_log_path(session_id)
        log_path.write_text(
            json.dumps({"type": LogEntryType.SESSION_START.value, "session_id": session_id, "timestamp": datetime.now().isoformat()}) + "\n" +
            json.dumps({"type": LogEntryType.SESSION_END.value, "outcome": "success", "timestamp": datetime.now().isoformat()}) + "\n"
        )

        # Set as current
        workspace.set_current_session(session_id)
        assert workspace.current_log.exists()

        # Run check and fix
        checker = WorkspaceHealthChecker(temp_project, workspace=workspace)
        report = checker.check_all()

        cleaner = WorkspaceCleaner(temp_project, workspace=workspace)
        fixed = cleaner.fix_auto(report)

        stale_fixed = [i for i in fixed if i.type == HealthIssueType.STALE_CURRENT]
        assert len(stale_fixed) == 1
        assert not workspace.current_log.exists()

    def test_fixes_orphan_log(self, temp_project):
        """Should add orphan logs to index."""
        workspace = WorkspaceManager(temp_project)

        # Create an orphan log
        session_id = "20240115_001_coding_orphan"
        log_path = workspace.get_session_log_path(session_id)
        log_path.write_text(
            json.dumps({
                "type": LogEntryType.SESSION_START.value,
                "session_id": session_id,
                "agent_type": "coding",
                "feature_id": "test-feature",
                "timestamp": datetime.now().isoformat()
            }) + "\n" +
            json.dumps({
                "type": LogEntryType.SESSION_END.value,
                "outcome": "success",
                "timestamp": datetime.now().isoformat()
            }) + "\n"
        )

        # Verify not in index
        index = workspace.get_session_index()
        assert index.get_session(session_id) is None

        # Run check and fix
        checker = WorkspaceHealthChecker(temp_project, workspace=workspace)
        report = checker.check_all()

        cleaner = WorkspaceCleaner(temp_project, workspace=workspace)
        fixed = cleaner.fix_auto(report)

        orphan_fixed = [i for i in fixed if i.type == HealthIssueType.ORPHAN_LOG]
        assert len(orphan_fixed) == 1

        # Verify now in index
        index = workspace.get_session_index()
        session = index.get_session(session_id)
        assert session is not None
        assert session.agent_type == "coding"
        assert session.feature_id == "test-feature"

    def test_fixes_missing_log(self, temp_project):
        """Should remove missing log references from index."""
        workspace = WorkspaceManager(temp_project)
        from autonomous_dev_agent.models import SessionIndexEntry

        # Add a session to index without creating the file
        workspace.update_session_index(SessionIndexEntry(
            session_id="20240115_001_coding_missing",
            file="sessions/20240115_001_coding_missing.jsonl",
            agent_type="coding",
            started_at=datetime.now(),
        ))

        # Verify in index but file doesn't exist
        index = workspace.get_session_index()
        assert index.get_session("20240115_001_coding_missing") is not None
        assert not workspace.get_session_log_path("20240115_001_coding_missing").exists()

        # Run check and fix
        checker = WorkspaceHealthChecker(temp_project, workspace=workspace)
        report = checker.check_all()

        cleaner = WorkspaceCleaner(temp_project, workspace=workspace)
        fixed = cleaner.fix_auto(report)

        missing_fixed = [i for i in fixed if i.type == HealthIssueType.MISSING_LOG]
        assert len(missing_fixed) == 1

        # Verify removed from index
        index = workspace.get_session_index()
        assert index.get_session("20240115_001_coding_missing") is None

    def test_does_not_fix_non_auto_fixable(self, temp_project):
        """Should not attempt to fix issues that aren't auto-fixable."""
        # Create a stale feature (not auto-fixable)
        backlog = Backlog(
            project_name="Test Project",
            project_path=str(temp_project),
            features=[
                Feature(
                    id="stale-feature",
                    name="Stale",
                    description="Stuck feature",
                    status=FeatureStatus.IN_PROGRESS
                ),
            ]
        )
        (temp_project / "feature-list.json").write_text(backlog.model_dump_json())

        checker = WorkspaceHealthChecker(temp_project)
        report = checker.check_all()

        stale_issues = [i for i in report.issues if i.type == HealthIssueType.STALE_FEATURE]
        assert len(stale_issues) == 1
        assert stale_issues[0].auto_fixable is False

        cleaner = WorkspaceCleaner(temp_project)
        fixed = cleaner.fix_auto(report)

        # Stale feature should not be in fixed list
        stale_fixed = [i for i in fixed if i.type == HealthIssueType.STALE_FEATURE]
        assert len(stale_fixed) == 0

        # Issue should still be in report
        assert len([i for i in report.issues if i.type == HealthIssueType.STALE_FEATURE]) == 1


class TestHealthReport:
    """Tests for HealthReport model."""

    def test_add_issue_updates_counts(self):
        """Adding issues should update severity counts."""
        report = HealthReport(project_path="/tmp/test")
        assert report.healthy is True
        assert report.critical_count == 0

        report.add_issue(HealthIssue(
            type=HealthIssueType.CORRUPT_INDEX,
            severity=HealthIssueSeverity.CRITICAL,
            message="Test critical"
        ))

        assert report.healthy is False
        assert report.critical_count == 1

        report.add_issue(HealthIssue(
            type=HealthIssueType.CRASHED_SESSION,
            severity=HealthIssueSeverity.WARNING,
            message="Test warning"
        ))

        assert report.warning_count == 1
        assert len(report.issues) == 2

    def test_mark_fixed_updates_counts(self):
        """Marking issues fixed should update counts."""
        report = HealthReport(project_path="/tmp/test")
        issue = HealthIssue(
            type=HealthIssueType.CRASHED_SESSION,
            severity=HealthIssueSeverity.WARNING,
            message="Test"
        )
        report.add_issue(issue)

        assert report.warning_count == 1
        assert report.healthy is False

        report.mark_fixed(issue)

        assert report.warning_count == 0
        assert report.healthy is True
        assert len(report.issues_fixed) == 1
