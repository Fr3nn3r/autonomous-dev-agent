"""Progress tracking - the key artifact for session handoffs.

Based on Anthropic's claude-progress.txt pattern: a simple text file that gives
each new session immediate context about what's been done and what's next.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import ProgressEntry, Feature


class ProgressTracker:
    """Manages the progress file that enables clean session handoffs.

    The progress file is intentionally plain text (not JSON) because:
    1. It's meant to be read by the next agent session as context
    2. Human-readable format for debugging and monitoring
    3. Append-only pattern prevents data loss
    """

    def __init__(self, project_path: Path, filename: str = "claude-progress.txt"):
        self.project_path = Path(project_path)
        self.progress_file = self.project_path / filename

    def read_progress(self) -> str:
        """Read the full progress file for session context."""
        if not self.progress_file.exists():
            return ""
        return self.progress_file.read_text(encoding="utf-8")

    def read_recent(self, lines: int = 50) -> str:
        """Read only recent progress for context efficiency."""
        if not self.progress_file.exists():
            return ""

        content = self.progress_file.read_text(encoding="utf-8")
        all_lines = content.strip().split("\n")

        if len(all_lines) <= lines:
            return content

        return "\n".join(["[... earlier progress truncated ...]\n"] + all_lines[-lines:])

    def append_entry(self, entry: ProgressEntry) -> None:
        """Append a progress entry to the file."""
        timestamp = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"\n{'='*60}",
            f"[{timestamp}] Session: {entry.session_id}",
            f"Action: {entry.action}",
        ]

        if entry.feature_id:
            lines.append(f"Feature: {entry.feature_id}")

        lines.append(f"\n{entry.summary}")

        if entry.files_changed:
            lines.append(f"\nFiles changed: {', '.join(entry.files_changed)}")

        if entry.commit_hash:
            lines.append(f"Commit: {entry.commit_hash}")

        lines.append("")

        with open(self.progress_file, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def log_session_start(self, session_id: str, feature: Optional[Feature] = None) -> None:
        """Log the start of a new session."""
        if feature:
            summary = f"Starting work on feature: {feature.name}\n\nDescription: {feature.description}"
            if feature.acceptance_criteria:
                summary += "\n\nAcceptance criteria:\n" + "\n".join(
                    f"  - {c}" for c in feature.acceptance_criteria
                )
        else:
            summary = "Starting new session (no specific feature assigned)"

        self.append_entry(ProgressEntry(
            session_id=session_id,
            feature_id=feature.id if feature else None,
            action="session_started",
            summary=summary
        ))

    def log_handoff(
        self,
        session_id: str,
        feature_id: Optional[str],
        summary: str,
        files_changed: list[str],
        commit_hash: Optional[str] = None,
        next_steps: Optional[str] = None
    ) -> None:
        """Log a handoff to the next session."""
        full_summary = f"HANDOFF: {summary}"
        if next_steps:
            full_summary += f"\n\nNEXT STEPS FOR INCOMING SESSION:\n{next_steps}"

        self.append_entry(ProgressEntry(
            session_id=session_id,
            feature_id=feature_id,
            action="handoff",
            summary=full_summary,
            files_changed=files_changed,
            commit_hash=commit_hash
        ))

    def log_feature_completed(
        self,
        session_id: str,
        feature: Feature,
        summary: str,
        commit_hash: Optional[str] = None
    ) -> None:
        """Log completion of a feature."""
        self.append_entry(ProgressEntry(
            session_id=session_id,
            feature_id=feature.id,
            action="feature_completed",
            summary=f"COMPLETED: {feature.name}\n\n{summary}",
            commit_hash=commit_hash
        ))

    def initialize(self, project_name: str) -> None:
        """Initialize a new progress file for a project."""
        if self.progress_file.exists():
            return  # Don't overwrite existing progress

        header = f"""# Claude Progress Log - {project_name}
# This file tracks agent progress across sessions.
# Each session reads this file to understand what's been done.
#
# Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

"""
        self.progress_file.write_text(header, encoding="utf-8")
