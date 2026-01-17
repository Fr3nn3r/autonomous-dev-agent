"""Git operations for the harness.

Handles commits, getting status, and maintaining recoverable states.
"""

import subprocess
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class GitStatus:
    """Current git status."""
    branch: str
    has_changes: bool
    staged_files: list[str]
    modified_files: list[str]
    untracked_files: list[str]
    last_commit_hash: Optional[str]
    last_commit_message: Optional[str]


class GitManager:
    """Manages git operations for the project."""

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command."""
        return subprocess.run(
            ["git", *args],
            cwd=self.project_path,
            capture_output=True,
            text=True,
            check=check
        )

    def is_git_repo(self) -> bool:
        """Check if the project is a git repository."""
        result = self._run("rev-parse", "--git-dir", check=False)
        return result.returncode == 0

    def init_repo(self) -> None:
        """Initialize a git repository if not exists."""
        if not self.is_git_repo():
            self._run("init")

    def get_status(self) -> GitStatus:
        """Get current git status."""
        # Get branch
        branch_result = self._run("branch", "--show-current", check=False)
        branch = branch_result.stdout.strip() or "main"

        # Get status
        status_result = self._run("status", "--porcelain", check=False)
        lines = status_result.stdout.strip().split("\n") if status_result.stdout.strip() else []

        staged = []
        modified = []
        untracked = []

        for line in lines:
            if not line:
                continue
            status_code = line[:2]
            filename = line[3:]

            if status_code[0] in "MADRC":
                staged.append(filename)
            if status_code[1] in "MD":
                modified.append(filename)
            if status_code == "??":
                untracked.append(filename)

        # Get last commit
        log_result = self._run("log", "-1", "--format=%H%n%s", check=False)
        if log_result.returncode == 0 and log_result.stdout.strip():
            parts = log_result.stdout.strip().split("\n", 1)
            last_hash = parts[0]
            last_message = parts[1] if len(parts) > 1 else ""
        else:
            last_hash = None
            last_message = None

        return GitStatus(
            branch=branch,
            has_changes=bool(staged or modified or untracked),
            staged_files=staged,
            modified_files=modified,
            untracked_files=untracked,
            last_commit_hash=last_hash,
            last_commit_message=last_message
        )

    def get_recent_commits(self, count: int = 5) -> list[tuple[str, str]]:
        """Get recent commit hashes and messages."""
        result = self._run("log", f"-{count}", "--format=%H|%s", check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                hash_, message = line.split("|", 1)
                commits.append((hash_, message))
        return commits

    def stage_all(self) -> None:
        """Stage all changes."""
        self._run("add", "-A")

    def commit(self, message: str, allow_empty: bool = False) -> Optional[str]:
        """Create a commit and return the hash."""
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")

        result = self._run(*args, check=False)
        if result.returncode != 0:
            return None

        # Get the new commit hash
        hash_result = self._run("rev-parse", "HEAD")
        return hash_result.stdout.strip()

    def get_diff_summary(self, staged_only: bool = False) -> str:
        """Get a summary of changes for commit message generation."""
        args = ["diff", "--stat"]
        if staged_only:
            args.append("--staged")

        result = self._run(*args, check=False)
        return result.stdout.strip()

    def get_changed_files(self, since_commit: Optional[str] = None) -> list[str]:
        """Get list of files changed since a commit (or all uncommitted)."""
        if since_commit:
            result = self._run("diff", "--name-only", since_commit, "HEAD", check=False)
        else:
            result = self._run("diff", "--name-only", "HEAD", check=False)

        if result.returncode != 0 or not result.stdout.strip():
            return []

        return result.stdout.strip().split("\n")
