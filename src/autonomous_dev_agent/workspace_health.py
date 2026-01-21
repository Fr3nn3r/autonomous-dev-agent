"""Workspace health checking and repair utilities.

Detects and fixes common workspace issues including:
- Crashed sessions (session_start without session_end)
- Stale current session pointers
- Orphan log files not in index
- Session ID collisions
- Uncommitted git work
- Stale features stuck in in_progress
- Corrupt or missing index entries
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    HealthIssue,
    HealthIssueSeverity,
    HealthIssueType,
    HealthReport,
    LogEntryType,
    FeatureStatus,
    Backlog,
)
from .workspace import WorkspaceManager
from .git_manager import GitManager


class WorkspaceHealthChecker:
    """Detects workspace health issues.

    Performs comprehensive checks on the .ada/ workspace including:
    - Session log integrity
    - Index consistency
    - Git state
    - Feature status
    """

    def __init__(
        self,
        project_path: Path,
        workspace: Optional[WorkspaceManager] = None,
        git: Optional[GitManager] = None,
        backlog_file: str = "feature-list.json"
    ):
        """Initialize the health checker.

        Args:
            project_path: Path to the project directory
            workspace: Optional WorkspaceManager instance (creates one if None)
            git: Optional GitManager instance (creates one if None)
            backlog_file: Name of the backlog file
        """
        self.project_path = Path(project_path).resolve()
        self.workspace = workspace or WorkspaceManager(self.project_path)
        self.git = git or GitManager(self.project_path)
        self.backlog_file = backlog_file

    def check_all(self) -> HealthReport:
        """Run all health checks and return a report.

        Returns:
            HealthReport with all issues found
        """
        report = HealthReport(project_path=str(self.project_path))

        # Only check if workspace exists
        if not self.workspace.exists():
            return report

        # Run all checks
        self._check_index_integrity(report)
        self._check_crashed_sessions(report)
        self._check_stale_current_session(report)
        self._check_orphan_logs(report)
        self._check_missing_logs(report)
        self._check_session_collisions(report)
        self._check_uncommitted_work(report)
        self._check_stale_features(report)

        return report

    def _check_index_integrity(self, report: HealthReport) -> None:
        """Check if index.json is readable and valid."""
        if not self.workspace.index_file.exists():
            return

        try:
            content = self.workspace.index_file.read_text(encoding="utf-8")
            json.loads(content)
        except json.JSONDecodeError as e:
            report.add_issue(HealthIssue(
                type=HealthIssueType.CORRUPT_INDEX,
                severity=HealthIssueSeverity.CRITICAL,
                message="Session index is corrupted",
                details=f"JSON parse error: {e}",
                file_path=str(self.workspace.index_file),
                auto_fixable=False,
                fix_description="Rebuild index from log files"
            ))
        except Exception as e:
            report.add_issue(HealthIssue(
                type=HealthIssueType.CORRUPT_INDEX,
                severity=HealthIssueSeverity.CRITICAL,
                message="Cannot read session index",
                details=str(e),
                file_path=str(self.workspace.index_file),
                auto_fixable=False
            ))

    def _check_crashed_sessions(self, report: HealthReport) -> None:
        """Check for sessions with session_start but no session_end."""
        if not self.workspace.sessions_dir.exists():
            return

        for log_file in self.workspace.sessions_dir.glob("*.jsonl"):
            has_start = False
            has_end = False
            session_id = log_file.stem

            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            entry_type = entry.get("type")
                            if entry_type == LogEntryType.SESSION_START.value:
                                has_start = True
                            elif entry_type == LogEntryType.SESSION_END.value:
                                has_end = True
                        except json.JSONDecodeError:
                            continue

                if has_start and not has_end:
                    report.add_issue(HealthIssue(
                        type=HealthIssueType.CRASHED_SESSION,
                        severity=HealthIssueSeverity.WARNING,
                        message=f"Session {session_id} appears to have crashed",
                        details="Log has session_start but no session_end",
                        session_id=session_id,
                        file_path=str(log_file),
                        auto_fixable=True,
                        fix_description="Append session_end with outcome=crashed"
                    ))
            except Exception as e:
                # If we can't read the log, report as info (might be locked)
                report.add_issue(HealthIssue(
                    type=HealthIssueType.CRASHED_SESSION,
                    severity=HealthIssueSeverity.INFO,
                    message=f"Cannot read session log: {session_id}",
                    details=str(e),
                    session_id=session_id,
                    file_path=str(log_file),
                    auto_fixable=False
                ))

    def _check_stale_current_session(self, report: HealthReport) -> None:
        """Check if current.jsonl points to an ended or missing session."""
        if not self.workspace.current_log.exists():
            return

        try:
            content = self.workspace.current_log.read_text(encoding="utf-8")
            data = json.loads(content)
            current_session_id = data.get("session_id")

            if not current_session_id:
                report.add_issue(HealthIssue(
                    type=HealthIssueType.STALE_CURRENT,
                    severity=HealthIssueSeverity.WARNING,
                    message="Current session reference is empty",
                    file_path=str(self.workspace.current_log),
                    auto_fixable=True,
                    fix_description="Delete current.jsonl"
                ))
                return

            # Check if the session file exists
            session_log = self.workspace.get_session_log_path(current_session_id)
            if not session_log.exists():
                report.add_issue(HealthIssue(
                    type=HealthIssueType.STALE_CURRENT,
                    severity=HealthIssueSeverity.WARNING,
                    message=f"Current session {current_session_id} log file missing",
                    session_id=current_session_id,
                    file_path=str(self.workspace.current_log),
                    auto_fixable=True,
                    fix_description="Delete current.jsonl"
                ))
                return

            # Check if the session has ended
            has_ended = False
            try:
                with open(session_log, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("type") == LogEntryType.SESSION_END.value:
                                has_ended = True
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass

            if has_ended:
                report.add_issue(HealthIssue(
                    type=HealthIssueType.STALE_CURRENT,
                    severity=HealthIssueSeverity.WARNING,
                    message=f"Current session {current_session_id} has already ended",
                    session_id=current_session_id,
                    file_path=str(self.workspace.current_log),
                    auto_fixable=True,
                    fix_description="Delete current.jsonl"
                ))

        except json.JSONDecodeError:
            report.add_issue(HealthIssue(
                type=HealthIssueType.STALE_CURRENT,
                severity=HealthIssueSeverity.WARNING,
                message="Current session reference is corrupted",
                file_path=str(self.workspace.current_log),
                auto_fixable=True,
                fix_description="Delete current.jsonl"
            ))

    def _check_orphan_logs(self, report: HealthReport) -> None:
        """Check for log files not in the index."""
        if not self.workspace.sessions_dir.exists():
            return

        index = self.workspace.get_session_index()
        indexed_files = {s.file.split("/")[-1] for s in index.sessions}

        for log_file in self.workspace.sessions_dir.glob("*.jsonl"):
            if log_file.name not in indexed_files:
                session_id = log_file.stem
                report.add_issue(HealthIssue(
                    type=HealthIssueType.ORPHAN_LOG,
                    severity=HealthIssueSeverity.INFO,
                    message=f"Log file {log_file.name} not in index",
                    session_id=session_id,
                    file_path=str(log_file),
                    auto_fixable=True,
                    fix_description="Add to index from log contents"
                ))

    def _check_missing_logs(self, report: HealthReport) -> None:
        """Check for index entries referencing non-existent files."""
        index = self.workspace.get_session_index()

        for session in index.sessions:
            if session.archived:
                continue  # Skip archived sessions

            log_path = self.workspace.sessions_dir / session.file.split("/")[-1]
            if not log_path.exists():
                report.add_issue(HealthIssue(
                    type=HealthIssueType.MISSING_LOG,
                    severity=HealthIssueSeverity.WARNING,
                    message=f"Index references missing log: {session.session_id}",
                    session_id=session.session_id,
                    file_path=str(log_path),
                    auto_fixable=True,
                    fix_description="Remove from index"
                ))

    def _check_session_collisions(self, report: HealthReport) -> None:
        """Check for sessions with the same date_seq prefix."""
        index = self.workspace.get_session_index()

        # Extract date_seq (e.g., "20240115_001") from session IDs
        prefixes: dict[str, list[str]] = {}
        for session in index.sessions:
            # Session ID format: {YYYYMMDD}_{NNN}_{type}_{feature}
            parts = session.session_id.split("_")
            if len(parts) >= 2:
                prefix = f"{parts[0]}_{parts[1]}"
                if prefix not in prefixes:
                    prefixes[prefix] = []
                prefixes[prefix].append(session.session_id)

        for prefix, session_ids in prefixes.items():
            if len(session_ids) > 1:
                report.add_issue(HealthIssue(
                    type=HealthIssueType.SESSION_COLLISION,
                    severity=HealthIssueSeverity.WARNING,
                    message=f"Session ID collision: {prefix}",
                    details=f"Conflicting sessions: {', '.join(session_ids)}",
                    auto_fixable=False,
                    fix_description="Manual rename required"
                ))

    def _check_uncommitted_work(self, report: HealthReport) -> None:
        """Check for uncommitted git changes."""
        if not self.git.is_git_repo():
            return

        try:
            status = self.git.get_status()
            if status.has_changes:
                total_changes = len(status.modified_files) + len(status.untracked_files)
                report.add_issue(HealthIssue(
                    type=HealthIssueType.UNCOMMITTED_WORK,
                    severity=HealthIssueSeverity.INFO,
                    message=f"Uncommitted changes: {total_changes} file(s)",
                    details=(
                        f"Modified: {len(status.modified_files)}, "
                        f"Untracked: {len(status.untracked_files)}"
                    ),
                    auto_fixable=False,
                    fix_description="User should commit or stash changes"
                ))
        except Exception:
            pass  # Git not available or error, skip this check

    def _check_stale_features(self, report: HealthReport) -> None:
        """Check for features stuck in in_progress without an active session."""
        backlog_path = self.project_path / self.backlog_file
        if not backlog_path.exists():
            return

        try:
            backlog_text = backlog_path.read_text(encoding="utf-8")
            backlog = Backlog.model_validate_json(backlog_text)
        except Exception:
            return  # Can't read backlog, skip this check

        # Get current session if any
        current_session_id = self.workspace.get_current_session_id()

        # Get current feature from session if we have one
        current_feature_id = None
        if current_session_id:
            session_log = self.workspace.get_session_log_path(current_session_id)
            if session_log.exists():
                try:
                    with open(session_log, "r", encoding="utf-8") as f:
                        first_line = f.readline()
                        if first_line:
                            entry = json.loads(first_line)
                            if entry.get("type") == LogEntryType.SESSION_START.value:
                                current_feature_id = entry.get("feature_id")
                except Exception:
                    pass

        # Check for in_progress features without active session
        for feature in backlog.features:
            if feature.status == FeatureStatus.IN_PROGRESS:
                if feature.id != current_feature_id:
                    report.add_issue(HealthIssue(
                        type=HealthIssueType.STALE_FEATURE,
                        severity=HealthIssueSeverity.WARNING,
                        message=f"Feature '{feature.name}' stuck in in_progress",
                        details="No active session is working on this feature",
                        feature_id=feature.id,
                        auto_fixable=False,
                        fix_description="User should reset to pending or resume work"
                    ))


class WorkspaceCleaner:
    """Fixes workspace health issues.

    Provides automatic fixes for safe issues and guided fixes for
    issues requiring user interaction.
    """

    def __init__(
        self,
        project_path: Path,
        workspace: Optional[WorkspaceManager] = None
    ):
        """Initialize the workspace cleaner.

        Args:
            project_path: Path to the project directory
            workspace: Optional WorkspaceManager instance
        """
        self.project_path = Path(project_path).resolve()
        self.workspace = workspace or WorkspaceManager(self.project_path)

    def fix_auto(self, report: HealthReport) -> list[HealthIssue]:
        """Fix all auto-fixable issues in the report.

        Args:
            report: HealthReport with issues to fix

        Returns:
            List of issues that were fixed
        """
        fixed = []

        # Create a copy of issues to iterate (we modify the list)
        issues_to_fix = [i for i in report.issues if i.auto_fixable]

        for issue in issues_to_fix:
            success = False

            if issue.type == HealthIssueType.CRASHED_SESSION:
                success = self._fix_crashed_session(issue)
            elif issue.type == HealthIssueType.STALE_CURRENT:
                success = self._fix_stale_current(issue)
            elif issue.type == HealthIssueType.ORPHAN_LOG:
                success = self._fix_orphan_log(issue)
            elif issue.type == HealthIssueType.MISSING_LOG:
                success = self._fix_missing_log(issue)

            if success:
                fixed.append(issue)
                report.mark_fixed(issue)

        return fixed

    def _fix_crashed_session(self, issue: HealthIssue) -> bool:
        """Fix a crashed session by appending session_end.

        Args:
            issue: HealthIssue for the crashed session

        Returns:
            True if fixed successfully
        """
        if not issue.session_id or not issue.file_path:
            return False

        log_path = Path(issue.file_path)
        if not log_path.exists():
            return False

        try:
            # Read the log to get session info
            session_info = {
                "agent_type": "coding",
                "feature_id": None,
                "started_at": None,
                "turns": 0,
                "total_tokens": 0,
            }

            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        entry_type = entry.get("type")
                        if entry_type == LogEntryType.SESSION_START.value:
                            session_info["agent_type"] = entry.get(
                                "agent_type", "coding"
                            )
                            session_info["feature_id"] = entry.get("feature_id")
                            session_info["started_at"] = entry.get("timestamp")
                        elif entry_type == LogEntryType.ASSISTANT.value:
                            turn = entry.get("turn", 0)
                            session_info["turns"] = max(session_info["turns"], turn)
                        elif entry_type == LogEntryType.CONTEXT_UPDATE.value:
                            session_info["total_tokens"] = entry.get(
                                "total_tokens", 0
                            )
                    except json.JSONDecodeError:
                        continue

            # Append session_end entry
            end_entry = {
                "type": LogEntryType.SESSION_END.value,
                "timestamp": datetime.now().isoformat(),
                "session_id": issue.session_id,
                "outcome": "crashed",
                "reason": "Session recovered by workspace health check",
                "duration_seconds": 0,
                "turns": session_info["turns"],
                "tokens": {
                    "input": session_info["total_tokens"],
                    "output": 0,
                    "cache_read": 0,
                    "cache_write": 0
                },
                "files_changed": [],
                "commit_hash": None,
                "handoff_notes": None
            }

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(end_entry, default=str) + "\n")

            # Update index if session exists
            index = self.workspace.get_session_index()
            existing = index.get_session(issue.session_id)
            if existing:
                index.update_session(
                    issue.session_id,
                    ended_at=datetime.now(),
                    outcome="crashed"
                )
                self.workspace._save_index(index)

            return True

        except Exception:
            return False

    def _fix_stale_current(self, issue: HealthIssue) -> bool:
        """Fix a stale current session pointer by deleting current.jsonl.

        Args:
            issue: HealthIssue for the stale current session

        Returns:
            True if fixed successfully
        """
        try:
            if self.workspace.current_log.exists():
                self.workspace.current_log.unlink()
            return True
        except Exception:
            return False

    def _fix_orphan_log(self, issue: HealthIssue) -> bool:
        """Fix an orphan log by adding it to the index.

        Args:
            issue: HealthIssue for the orphan log

        Returns:
            True if fixed successfully
        """
        if not issue.session_id or not issue.file_path:
            return False

        log_path = Path(issue.file_path)
        if not log_path.exists():
            return False

        try:
            # Read the log to extract session info
            from .models import SessionIndexEntry

            session_info = {
                "session_id": issue.session_id,
                "agent_type": "coding",
                "feature_id": None,
                "started_at": datetime.now(),
                "ended_at": None,
                "outcome": None,
                "turns": 0,
                "tokens_total": 0,
            }

            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        entry_type = entry.get("type")
                        if entry_type == LogEntryType.SESSION_START.value:
                            session_info["agent_type"] = entry.get(
                                "agent_type", "coding"
                            )
                            session_info["feature_id"] = entry.get("feature_id")
                            if entry.get("timestamp"):
                                ts = entry["timestamp"].replace("Z", "+00:00")
                                session_info["started_at"] = datetime.fromisoformat(ts)
                        elif entry_type == LogEntryType.ASSISTANT.value:
                            turn = entry.get("turn", 0)
                            session_info["turns"] = max(session_info["turns"], turn)
                        elif entry_type == LogEntryType.CONTEXT_UPDATE.value:
                            session_info["tokens_total"] = entry.get(
                                "total_tokens", 0
                            )
                        elif entry_type == LogEntryType.SESSION_END.value:
                            session_info["outcome"] = entry.get("outcome")
                            if entry.get("timestamp"):
                                session_info["ended_at"] = datetime.fromisoformat(
                                    entry["timestamp"].replace("Z", "+00:00")
                                )
                    except (json.JSONDecodeError, ValueError):
                        continue

            # Create index entry
            entry = SessionIndexEntry(
                session_id=issue.session_id,
                file=f"sessions/{log_path.name}",
                agent_type=session_info["agent_type"],
                feature_id=session_info["feature_id"],
                started_at=session_info["started_at"],
                ended_at=session_info["ended_at"],
                outcome=session_info["outcome"],
                turns=session_info["turns"],
                tokens_total=session_info["tokens_total"],
                size_bytes=log_path.stat().st_size
            )

            self.workspace.update_session_index(entry)
            return True

        except Exception:
            return False

    def _fix_missing_log(self, issue: HealthIssue) -> bool:
        """Fix a missing log by removing it from the index.

        Args:
            issue: HealthIssue for the missing log

        Returns:
            True if fixed successfully
        """
        if not issue.session_id:
            return False

        try:
            index = self.workspace.get_session_index()

            # Filter out the missing session
            index.sessions = [
                s for s in index.sessions if s.session_id != issue.session_id
            ]
            index.total_sessions = len(index.sessions)
            index.total_size_bytes = sum(
                s.size_bytes for s in index.sessions if not s.archived
            )

            self.workspace._save_index(index)
            return True

        except Exception:
            return False
