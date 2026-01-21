"""Workspace management for the .ada/ directory structure.

Handles creation and maintenance of the .ada/ workspace including:
- Directory structure creation
- Project context management (project.json)
- Session index management (index.json)
- Log rotation and archiving
"""

import json
import os
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import ProjectContext, SessionIndex, SessionIndexEntry


class WorkspaceManager:
    """Manages the .ada/ workspace directory structure.

    Directory structure:
        .ada/
        ├── project.json            # Project metadata
        ├── config.json             # Optional harness config overrides
        ├── logs/
        │   ├── sessions/           # JSONL session logs
        │   │   └── {date}_{seq}_{type}_{feature}.jsonl
        │   ├── index.json          # Session index
        │   ├── current.jsonl       # Copy of active session
        │   └── archive/            # Archived logs
        ├── state/
        │   ├── session.json        # Current session state
        │   └── history.json        # Session history
        ├── alerts.json             # Alert notifications
        ├── prompts/                # Custom prompt overrides
        ├── hooks/                  # Validation hooks
        └── baselines/              # Visual regression baselines
    """

    # Size limit for logs before rotation (100MB)
    LOG_ROTATION_THRESHOLD_BYTES = 100 * 1024 * 1024

    # Number of sessions to keep unarchived
    SESSIONS_TO_KEEP = 50

    def __init__(self, project_path: Path):
        """Initialize workspace manager.

        Args:
            project_path: Path to the project directory
        """
        self.project_path = Path(project_path).resolve()
        self.ada_dir = self.project_path / ".ada"
        self.logs_dir = self.ada_dir / "logs"
        self.sessions_dir = self.logs_dir / "sessions"
        self.archive_dir = self.logs_dir / "archive"
        self.state_dir = self.ada_dir / "state"
        self.prompts_dir = self.ada_dir / "prompts"
        self.hooks_dir = self.ada_dir / "hooks"
        self.baselines_dir = self.ada_dir / "baselines"

        # File paths
        self.project_file = self.ada_dir / "project.json"
        self.config_file = self.ada_dir / "config.json"
        self.index_file = self.logs_dir / "index.json"
        self.current_log = self.logs_dir / "current.jsonl"
        self.alerts_file = self.ada_dir / "alerts.json"
        self.session_state_file = self.state_dir / "session.json"
        self.session_history_file = self.state_dir / "history.json"

    def ensure_structure(self) -> None:
        """Create the .ada/ directory structure if it doesn't exist."""
        # Create directories
        self.ada_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.sessions_dir.mkdir(exist_ok=True)
        self.state_dir.mkdir(exist_ok=True)

        # These may already exist from previous versions
        self.prompts_dir.mkdir(exist_ok=True)
        self.hooks_dir.mkdir(exist_ok=True)
        self.baselines_dir.mkdir(exist_ok=True)

        # Initialize index if it doesn't exist
        if not self.index_file.exists():
            index = SessionIndex()
            self._save_index(index)

    def exists(self) -> bool:
        """Check if the workspace exists."""
        return self.ada_dir.exists()

    # =========================================================================
    # Project Context Management
    # =========================================================================

    def get_project_context(self) -> Optional[ProjectContext]:
        """Load project context from project.json.

        Returns:
            ProjectContext if exists, None otherwise
        """
        if not self.project_file.exists():
            return None

        try:
            data = json.loads(self.project_file.read_text(encoding="utf-8"))
            return ProjectContext.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            print(f"[WorkspaceManager] Warning: Could not load project.json: {e}")
            return None

    def save_project_context(self, context: ProjectContext) -> None:
        """Save project context to project.json.

        Args:
            context: Project context to save
        """
        self.ensure_structure()
        self.project_file.write_text(
            context.model_dump_json(indent=2),
            encoding="utf-8"
        )

    def create_project_context(
        self,
        name: str,
        description: str = "",
        created_by: str = "user",
        init_session: Optional[dict] = None
    ) -> ProjectContext:
        """Create a new project context.

        Args:
            name: Project name
            description: Project description
            created_by: Who created the project
            init_session: Optional dict with init session info (spec_file, model, etc.)

        Returns:
            Created ProjectContext
        """
        context = ProjectContext(
            name=name,
            description=description,
            created_at=datetime.now(),
            created_by=created_by,
            init_session=init_session
        )
        self.save_project_context(context)
        return context

    # =========================================================================
    # Session Index Management
    # =========================================================================

    def get_session_index(self) -> SessionIndex:
        """Load the session index.

        Returns:
            SessionIndex (empty if doesn't exist)
        """
        if not self.index_file.exists():
            return SessionIndex()

        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8"))
            return SessionIndex.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            print(f"[WorkspaceManager] Warning: Could not load index.json: {e}")
            return SessionIndex()

    def _save_index(self, index: SessionIndex) -> None:
        """Save the session index.

        Args:
            index: Session index to save
        """
        self.index_file.write_text(
            index.model_dump_json(indent=2),
            encoding="utf-8"
        )

    def update_session_index(self, entry: SessionIndexEntry) -> None:
        """Add or update a session in the index.

        Args:
            entry: Session index entry to add/update
        """
        self.ensure_structure()
        index = self.get_session_index()

        # Check if session exists
        existing = index.get_session(entry.session_id)
        if existing:
            index.update_session(entry.session_id, **entry.model_dump())
        else:
            index.add_session(entry)

        self._save_index(index)

    def get_next_session_id(
        self,
        agent_type: str = "coding",
        feature_id: Optional[str] = None
    ) -> str:
        """Generate the next session ID.

        Format: {YYYYMMDD}_{NNN}_{type}_{feature}

        Args:
            agent_type: Type of agent (initializer or coding)
            feature_id: Feature ID being worked on

        Returns:
            Session ID string
        """
        index = self.get_session_index()
        date_str = datetime.now().strftime("%Y%m%d")

        # Count sessions today
        today_count = sum(
            1 for s in index.sessions
            if s.session_id.startswith(date_str)
        )

        seq = today_count + 1
        seq_str = f"{seq:03d}"

        if feature_id:
            # Sanitize feature_id for filename
            safe_feature = feature_id.replace("/", "-").replace("\\", "-")[:30]
            return f"{date_str}_{seq_str}_{agent_type}_{safe_feature}"
        else:
            return f"{date_str}_{seq_str}_{agent_type}"

    def get_session_log_path(self, session_id: str) -> Path:
        """Get the path to a session log file.

        Args:
            session_id: Session ID

        Returns:
            Path to the session log file
        """
        return self.sessions_dir / f"{session_id}.jsonl"

    # =========================================================================
    # Log Rotation and Archiving
    # =========================================================================

    def get_logs_size_bytes(self) -> int:
        """Get total size of all log files in bytes.

        Returns:
            Total size in bytes
        """
        total = 0
        if self.sessions_dir.exists():
            for f in self.sessions_dir.iterdir():
                if f.is_file() and f.suffix == ".jsonl":
                    total += f.stat().st_size
        return total

    def should_rotate(self) -> bool:
        """Check if logs should be rotated.

        Returns:
            True if logs exceed the rotation threshold
        """
        return self.get_logs_size_bytes() > self.LOG_ROTATION_THRESHOLD_BYTES

    def rotate_logs(self) -> Optional[Path]:
        """Archive old session logs to reduce storage.

        Strategy:
        1. Keep the most recent SESSIONS_TO_KEEP sessions
        2. Archive older sessions to archive/YYYYMM.tar.gz
        3. Update index.json with archive references

        Returns:
            Path to the created archive, or None if nothing to archive
        """
        index = self.get_session_index()

        # Sort sessions by date (oldest first)
        sorted_sessions = sorted(
            index.sessions,
            key=lambda s: s.started_at
        )

        # Identify sessions to archive
        sessions_to_archive = sorted_sessions[:-self.SESSIONS_TO_KEEP]

        if not sessions_to_archive:
            return None

        # Create archive directory
        self.archive_dir.mkdir(exist_ok=True)

        # Group sessions by month for archiving
        by_month: dict[str, list[SessionIndexEntry]] = {}
        for session in sessions_to_archive:
            month_key = session.started_at.strftime("%Y%m")
            if month_key not in by_month:
                by_month[month_key] = []
            by_month[month_key].append(session)

        last_archive: Optional[Path] = None

        # Create archives for each month
        for month_key, sessions in by_month.items():
            archive_path = self.archive_dir / f"{month_key}.tar.gz"

            # Append to existing archive or create new
            mode = "a:gz" if archive_path.exists() else "w:gz"

            with tarfile.open(archive_path, mode) as tar:
                for session in sessions:
                    log_file = self.sessions_dir / session.file.split("/")[-1]
                    if log_file.exists():
                        tar.add(log_file, arcname=log_file.name)
                        log_file.unlink()  # Remove after archiving

            # Update index entries
            archive_name = f"archive/{month_key}.tar.gz"
            for session in sessions:
                index.update_session(
                    session.session_id,
                    archived=True,
                    archive_file=archive_name
                )

            last_archive = archive_path

        # Recalculate total size
        index.total_size_bytes = sum(
            s.size_bytes for s in index.sessions if not s.archived
        )

        self._save_index(index)

        return last_archive

    # =========================================================================
    # Current Session Management
    # =========================================================================

    def set_current_session(self, session_id: str) -> None:
        """Set the current active session.

        Creates/updates current.jsonl as a copy of the active session file.
        On Unix systems, this would be a symlink, but Windows doesn't always
        support symlinks, so we use a reference file instead.

        Args:
            session_id: Active session ID
        """
        session_file = self.get_session_log_path(session_id)

        # On Windows, write a reference file instead of symlink
        # The actual streaming happens through the session file directly
        self.current_log.write_text(
            json.dumps({"session_id": session_id, "file": str(session_file)}),
            encoding="utf-8"
        )

    def get_current_session_id(self) -> Optional[str]:
        """Get the current active session ID.

        Returns:
            Session ID or None if no active session
        """
        if not self.current_log.exists():
            return None

        try:
            data = json.loads(self.current_log.read_text(encoding="utf-8"))
            return data.get("session_id")
        except (json.JSONDecodeError, KeyError):
            return None

    def clear_current_session(self) -> None:
        """Clear the current session reference."""
        if self.current_log.exists():
            self.current_log.unlink()

    # =========================================================================
    # Migration Helpers
    # =========================================================================

    def get_legacy_state_file(self) -> Optional[Path]:
        """Get the path to legacy .ada_session_state.json if it exists.

        Returns:
            Path if exists, None otherwise
        """
        legacy = self.project_path / ".ada_session_state.json"
        return legacy if legacy.exists() else None

    def get_legacy_history_file(self) -> Optional[Path]:
        """Get the path to legacy .ada_session_history.json if it exists.

        Returns:
            Path if exists, None otherwise
        """
        legacy = self.project_path / ".ada_session_history.json"
        return legacy if legacy.exists() else None

    def get_legacy_alerts_file(self) -> Optional[Path]:
        """Get the path to legacy .ada_alerts.json if it exists.

        Returns:
            Path if exists, None otherwise
        """
        legacy = self.project_path / ".ada_alerts.json"
        return legacy if legacy.exists() else None

    def migrate_legacy_files(self) -> dict[str, bool]:
        """Migrate legacy state files to new locations.

        Returns:
            Dict mapping file type to success status
        """
        self.ensure_structure()
        results = {}

        # Migrate session state
        legacy_state = self.get_legacy_state_file()
        if legacy_state:
            try:
                shutil.move(str(legacy_state), str(self.session_state_file))
                results["session_state"] = True
            except Exception as e:
                print(f"[WorkspaceManager] Could not migrate session state: {e}")
                results["session_state"] = False

        # Migrate session history
        legacy_history = self.get_legacy_history_file()
        if legacy_history:
            try:
                shutil.move(str(legacy_history), str(self.session_history_file))
                results["session_history"] = True
            except Exception as e:
                print(f"[WorkspaceManager] Could not migrate session history: {e}")
                results["session_history"] = False

        # Migrate alerts
        legacy_alerts = self.get_legacy_alerts_file()
        if legacy_alerts:
            try:
                shutil.move(str(legacy_alerts), str(self.alerts_file))
                results["alerts"] = True
            except Exception as e:
                print(f"[WorkspaceManager] Could not migrate alerts: {e}")
                results["alerts"] = False

        return results

    def update_gitignore(self) -> bool:
        """Update .gitignore with .ada/ patterns.

        Returns:
            True if .gitignore was updated
        """
        gitignore = self.project_path / ".gitignore"

        patterns = [
            "# ADA workspace (logs contain sensitive data)",
            ".ada/logs/",
            ".ada/state/",
            ".ada/alerts.json",
            "",
            "# Legacy ADA files (can be removed after migration)",
            ".ada_session_state.json",
            ".ada_session_history.json",
            ".ada_alerts.json",
        ]

        # Read existing content
        existing = ""
        if gitignore.exists():
            existing = gitignore.read_text(encoding="utf-8")

        # Check if already has ADA section
        if ".ada/logs/" in existing:
            return False

        # Add patterns
        new_content = existing
        if existing and not existing.endswith("\n"):
            new_content += "\n"
        if existing:
            new_content += "\n"
        new_content += "\n".join(patterns) + "\n"

        gitignore.write_text(new_content, encoding="utf-8")
        return True

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_workspace_stats(self) -> dict:
        """Get statistics about the workspace.

        Returns:
            Dict with workspace statistics
        """
        index = self.get_session_index()
        project = self.get_project_context()

        # Calculate totals from index
        total_tokens = sum(s.tokens_total for s in index.sessions)
        total_duration = 0
        for s in index.sessions:
            if s.started_at and s.ended_at:
                total_duration += (s.ended_at - s.started_at).total_seconds()

        # Count by outcome
        outcomes: dict[str, int] = {}
        for s in index.sessions:
            outcome = s.outcome or "unknown"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

        return {
            "project_name": project.name if project else "Unknown",
            "project_description": project.description if project else "",
            "created_at": project.created_at.isoformat() if project else None,
            "init_session": project.init_session if project else None,
            "total_sessions": index.total_sessions,
            "total_tokens": total_tokens,
            "total_duration_seconds": total_duration,
            "log_size_bytes": self.get_logs_size_bytes(),
            "log_size_mb": self.get_logs_size_bytes() / (1024 * 1024),
            "rotation_threshold_mb": self.LOG_ROTATION_THRESHOLD_BYTES / (1024 * 1024),
            "outcomes": outcomes,
        }
