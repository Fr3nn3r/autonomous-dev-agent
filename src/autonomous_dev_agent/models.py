"""Data models for the autonomous dev agent harness.

Uses Pydantic for validation. JSON format prevents accidental corruption by LLMs.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class FeatureStatus(str, Enum):
    """Status of a feature in the backlog."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class ErrorCategory(str, Enum):
    """Classification of errors for retry decisions.

    Categories determine whether to retry and how long to wait.
    """
    TRANSIENT = "transient"      # Network, timeout - retry with short delay
    RATE_LIMIT = "rate_limit"    # 429 - retry with longer delay
    SDK_CRASH = "sdk_crash"      # Windows exit code 1 - retry
    BILLING = "billing"          # Out of credits - stop
    AUTH = "auth"                # Invalid API key - stop
    UNKNOWN = "unknown"          # Unexpected - retry once, then stop


class FeatureCategory(str, Enum):
    """Category of feature work."""
    FUNCTIONAL = "functional"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    INFRASTRUCTURE = "infrastructure"


class QualityGates(BaseModel):
    """Optional quality gates for a feature.

    Quality gates are validation checks that must pass before a feature
    can be marked as complete. They help prevent common issues like:
    - Missing tests
    - Bloated files
    - Security vulnerabilities
    - Lint/type errors
    """
    require_tests: bool = Field(
        default=False,
        description="Require tests to exist for this feature"
    )
    max_file_lines: Optional[int] = Field(
        default=None,
        description="Maximum lines per file (e.g., 400 to prevent bloat)"
    )
    security_checklist: list[str] = Field(
        default_factory=list,
        description="Security items to verify (shown to agent in prompt)"
    )
    lint_command: Optional[str] = Field(
        default=None,
        description="Lint command to run (e.g., 'ruff check .')"
    )
    type_check_command: Optional[str] = Field(
        default=None,
        description="Type check command (e.g., 'pyright', 'mypy')"
    )
    custom_validators: list[str] = Field(
        default_factory=list,
        description="Custom shell commands that must exit 0"
    )


class Feature(BaseModel):
    """A single feature/task in the backlog.

    Based on Anthropic's recommendation for JSON-structured feature lists
    that are harder for models to accidentally corrupt.
    """
    id: str = Field(..., description="Unique identifier for the feature")
    name: str = Field(..., description="Short name for the feature")
    description: str = Field(..., description="Detailed description of what to implement")
    category: FeatureCategory = Field(default=FeatureCategory.FUNCTIONAL)
    status: FeatureStatus = Field(default=FeatureStatus.PENDING)
    priority: int = Field(default=0, description="Higher number = higher priority")

    # Acceptance criteria - explicit steps to verify completion
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Steps to verify the feature works correctly"
    )

    # Dependencies
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of features this depends on"
    )

    # Tracking
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sessions_spent: int = Field(default=0, description="Number of agent sessions spent on this")

    # Notes from agents
    implementation_notes: list[str] = Field(
        default_factory=list,
        description="Notes left by agents during implementation"
    )

    # Quality gates - optional validation requirements
    quality_gates: Optional[QualityGates] = Field(
        default=None,
        description="Quality gates that must pass before completion"
    )


class Backlog(BaseModel):
    """The full feature backlog for a project."""
    project_name: str
    project_path: str = Field(..., description="Absolute path to the project root")
    features: list[Feature] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    def get_next_feature(self) -> Optional[Feature]:
        """Get the highest priority pending/in_progress feature with satisfied dependencies."""
        completed_ids = {f.id for f in self.features if f.status == FeatureStatus.COMPLETED}

        candidates = [
            f for f in self.features
            if f.status in (FeatureStatus.PENDING, FeatureStatus.IN_PROGRESS)
            and all(dep in completed_ids for dep in f.depends_on)
        ]

        if not candidates:
            return None

        # Sort by: in_progress first, then by priority (descending)
        candidates.sort(
            key=lambda f: (f.status != FeatureStatus.IN_PROGRESS, -f.priority)
        )
        return candidates[0]

    def is_complete(self) -> bool:
        """Check if all features are completed."""
        return all(f.status == FeatureStatus.COMPLETED for f in self.features)

    def mark_feature_started(self, feature_id: str) -> None:
        """Mark a feature as in progress."""
        for f in self.features:
            if f.id == feature_id:
                f.status = FeatureStatus.IN_PROGRESS
                f.started_at = datetime.now()
                f.sessions_spent += 1
                self.last_updated = datetime.now()
                return
        raise ValueError(f"Feature {feature_id} not found")

    def mark_feature_completed(self, feature_id: str, notes: Optional[str] = None) -> None:
        """Mark a feature as completed."""
        for f in self.features:
            if f.id == feature_id:
                f.status = FeatureStatus.COMPLETED
                f.completed_at = datetime.now()
                if notes:
                    f.implementation_notes.append(notes)
                self.last_updated = datetime.now()
                return
        raise ValueError(f"Feature {feature_id} not found")

    def add_implementation_note(self, feature_id: str, note: str) -> None:
        """Add a note to a feature."""
        for f in self.features:
            if f.id == feature_id:
                f.implementation_notes.append(note)
                self.last_updated = datetime.now()
                return
        raise ValueError(f"Feature {feature_id} not found")


class ProgressEntry(BaseModel):
    """A single entry in the progress log."""
    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: str
    feature_id: Optional[str] = None
    action: str  # e.g., "started", "committed", "completed", "handoff"
    summary: str  # What was accomplished
    files_changed: list[str] = Field(default_factory=list)
    commit_hash: Optional[str] = None


class SessionState(BaseModel):
    """State persisted between sessions for recovery."""
    session_id: str
    started_at: datetime = Field(default_factory=datetime.now)
    current_feature_id: Optional[str] = None
    context_usage_percent: float = 0.0
    last_commit_hash: Optional[str] = None
    handoff_notes: Optional[str] = None


class SessionMode(str, Enum):
    """How to invoke Claude for agent sessions."""
    CLI = "cli"      # Direct CLI invocation (uses Claude subscription, more reliable)
    SDK = "sdk"      # Claude Agent SDK (uses API credits, streaming but less reliable on Windows)


class RetryConfig(BaseModel):
    """Configuration for retry logic with exponential backoff.

    Used by the harness to handle transient errors automatically.
    """
    max_retries: int = Field(
        default=3,
        description="Maximum retry attempts before giving up"
    )
    base_delay_seconds: float = Field(
        default=5.0,
        description="Initial delay between retries"
    )
    max_delay_seconds: float = Field(
        default=300.0,
        description="Maximum delay between retries (5 minutes)"
    )
    exponential_base: float = Field(
        default=2.0,
        description="Multiplier for exponential backoff"
    )
    jitter_factor: float = Field(
        default=0.1,
        description="Random jitter factor (0.1 = +/- 10%)"
    )
    retryable_categories: list[ErrorCategory] = Field(
        default_factory=lambda: [
            ErrorCategory.TRANSIENT,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.SDK_CRASH,
        ],
        description="Error categories that should be retried"
    )


class HarnessConfig(BaseModel):
    """Configuration for the harness."""
    # Context management
    context_threshold_percent: float = Field(
        default=70.0,
        description="Trigger handoff when context reaches this percentage"
    )

    # Session mode - CLI is default because SDK has reliability issues on Windows
    session_mode: SessionMode = Field(
        default=SessionMode.CLI,
        description="How to invoke Claude: 'cli' (direct CLI, uses subscription, more reliable) or 'sdk' (Agent SDK, uses API credits, Windows issues)"
    )

    # Model settings - different defaults for CLI vs SDK
    model: str = Field(
        default="claude-opus-4-5-20251101",
        description="Model to use. CLI mode supports any model, SDK may have restrictions."
    )

    # Paths
    progress_file: str = Field(default="claude-progress.txt")
    backlog_file: str = Field(default="feature-list.json")
    init_script: str = Field(default="init.sh")

    # Behavior
    auto_commit: bool = Field(default=True, description="Auto-commit on handoff")
    run_tests_before_commit: bool = Field(default=True)
    max_sessions: Optional[int] = Field(
        default=None,
        description="Maximum sessions before stopping (None = unlimited)"
    )

    # Testing
    test_command: Optional[str] = Field(
        default=None,
        description="Command to run tests before marking feature complete (e.g., 'pytest', 'npm test')"
    )

    # Retry configuration
    retry: RetryConfig = Field(
        default_factory=RetryConfig,
        description="Retry configuration for transient errors"
    )

    # Session timeout
    session_timeout_seconds: int = Field(
        default=1800,  # 30 minutes
        description="Maximum duration per session before forced handoff"
    )

    # SDK permissions (only used in SDK mode)
    allowed_tools: list[str] = Field(
        default_factory=lambda: [
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
            "WebFetch", "WebSearch"
        ]
    )

    # CLI options
    cli_max_turns: int = Field(
        default=100,
        description="Maximum agentic turns for CLI mode (prevents runaway sessions)"
    )

    # Quality gates - defaults applied to all features unless overridden
    default_quality_gates: Optional[QualityGates] = Field(
        default=None,
        description="Default quality gates for all features"
    )

    # Progress file rotation
    progress_rotation_threshold_kb: int = Field(
        default=50,
        description="Rotate progress file when it exceeds this size in KB"
    )
    progress_keep_entries: int = Field(
        default=100,
        description="Number of recent entries to keep after rotation"
    )
