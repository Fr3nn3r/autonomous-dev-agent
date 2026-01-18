"""Incremental discovery state tracker.

Tracks which issues have been seen and resolved across discovery runs.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import (
    BestPracticeViolation,
    CodeIssue,
    DiscoveryResult,
    DiscoveryState,
    TestGap,
)


# State file name
DISCOVERY_STATE_FILE = ".ada_discovery_state.json"


class DiscoveryTracker:
    """Tracks discovery state for incremental analysis."""

    def __init__(self, project_path: Path | str):
        """Initialize the tracker.

        Args:
            project_path: Path to the project root directory.
        """
        self.project_path = Path(project_path).resolve()
        self.state_file = self.project_path / DISCOVERY_STATE_FILE
        self._state: DiscoveryState | None = None

    @property
    def state(self) -> DiscoveryState:
        """Get the current state, loading from file if needed.

        Returns:
            Current DiscoveryState.
        """
        if self._state is None:
            self._state = self.load_state()
        return self._state

    def load_state(self) -> DiscoveryState:
        """Load discovery state from file.

        Returns:
            Loaded DiscoveryState or new state if file doesn't exist.
        """
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                return DiscoveryState.model_validate(data)
            except (json.JSONDecodeError, ValueError):
                # Corrupted state file - start fresh
                pass

        return DiscoveryState(project_path=str(self.project_path))

    def save_state(self) -> None:
        """Save the current state to file."""
        if self._state is None:
            return

        self._state.last_run_at = datetime.now()
        self._state.last_commit_hash = self.get_current_commit()

        data = self._state.model_dump(mode="json")
        # Handle datetime serialization
        if data.get("last_run_at"):
            data["last_run_at"] = self._state.last_run_at.isoformat()

        self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_current_commit(self) -> str | None:
        """Get the current git commit hash.

        Returns:
            Current commit hash or None if not a git repo.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None

    def has_changes_since_last_run(self) -> bool:
        """Check if there have been changes since the last discovery run.

        Returns:
            True if there are changes or no previous run.
        """
        if self.state.last_commit_hash is None:
            return True

        current_commit = self.get_current_commit()
        if current_commit is None:
            return True

        return current_commit != self.state.last_commit_hash

    def get_changed_files(self) -> list[str]:
        """Get list of files changed since last discovery run.

        Returns:
            List of changed file paths.
        """
        if self.state.last_commit_hash is None:
            return []

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", self.state.last_commit_hash, "HEAD"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return []

    def filter_new_issues(self, result: DiscoveryResult) -> DiscoveryResult:
        """Filter discovery result to only include new issues.

        Args:
            result: Full discovery result.

        Returns:
            Filtered result with only new issues.
        """
        # Filter code issues
        new_code_issues = [
            issue for issue in result.code_issues
            if not self.state.is_known(issue.id) and not self.state.is_resolved(issue.id)
        ]

        # Filter test gaps
        new_test_gaps = [
            gap for gap in result.test_gaps
            if not self.state.is_known(gap.id) and not self.state.is_resolved(gap.id)
        ]

        # Filter best practice violations
        new_violations = [
            v for v in result.best_practice_violations
            if not self.state.is_known(v.id) and not self.state.is_resolved(v.id)
        ]

        return DiscoveryResult(
            project_path=result.project_path,
            summary=result.summary,
            code_issues=new_code_issues,
            test_gaps=new_test_gaps,
            best_practice_violations=new_violations,
            discovered_at=result.discovered_at,
        )

    def mark_issues_known(self, result: DiscoveryResult) -> None:
        """Mark all issues in a result as known.

        Args:
            result: Discovery result with issues to mark.
        """
        for issue in result.code_issues:
            self.state.mark_known(issue.id)

        for gap in result.test_gaps:
            self.state.mark_known(gap.id)

        for violation in result.best_practice_violations:
            self.state.mark_known(violation.id)

    def mark_resolved(self, issue_id: str) -> None:
        """Mark an issue as resolved.

        Args:
            issue_id: ID of the resolved issue.
        """
        self.state.mark_resolved(issue_id)

    def find_resolved_issues(self, result: DiscoveryResult) -> list[str]:
        """Find issues that were previously known but are no longer present.

        Args:
            result: Current discovery result.

        Returns:
            List of resolved issue IDs.
        """
        # Get all current issue IDs
        current_ids: set[str] = set()
        for issue in result.code_issues:
            current_ids.add(issue.id)
        for gap in result.test_gaps:
            current_ids.add(gap.id)
        for violation in result.best_practice_violations:
            current_ids.add(violation.id)

        # Find known issues that are no longer present
        resolved = []
        for known_id in self.state.known_issue_ids:
            if known_id not in current_ids and known_id not in self.state.resolved_issue_ids:
                resolved.append(known_id)

        return resolved

    def update_from_result(
        self,
        result: DiscoveryResult,
        mark_resolved: bool = True,
    ) -> tuple[list[str], list[str]]:
        """Update state from a discovery result.

        Args:
            result: Discovery result to update from.
            mark_resolved: Whether to mark absent issues as resolved.

        Returns:
            Tuple of (new issue IDs, resolved issue IDs).
        """
        # Find new issues
        new_ids = []
        for issue in result.code_issues:
            if not self.state.is_known(issue.id):
                new_ids.append(issue.id)

        for gap in result.test_gaps:
            if not self.state.is_known(gap.id):
                new_ids.append(gap.id)

        for violation in result.best_practice_violations:
            if not self.state.is_known(violation.id):
                new_ids.append(violation.id)

        # Find resolved issues
        resolved_ids = []
        if mark_resolved:
            resolved_ids = self.find_resolved_issues(result)
            for issue_id in resolved_ids:
                self.state.mark_resolved(issue_id)

        # Mark all current issues as known
        self.mark_issues_known(result)

        return new_ids, resolved_ids

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about tracked issues.

        Returns:
            Dictionary with statistics.
        """
        return {
            "total_known": len(self.state.known_issue_ids),
            "total_resolved": len(self.state.resolved_issue_ids),
            "last_commit": self.state.last_commit_hash[:8] if self.state.last_commit_hash else None,
            "last_run": self.state.last_run_at.isoformat() if self.state.last_run_at else None,
        }

    def reset(self) -> None:
        """Reset tracking state (clears all known/resolved issues)."""
        self._state = DiscoveryState(project_path=str(self.project_path))
        if self.state_file.exists():
            self.state_file.unlink()
