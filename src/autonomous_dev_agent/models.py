"""Data models for the autonomous dev agent harness.

Uses Pydantic for validation. JSON format prevents accidental corruption by LLMs.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Literal

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

    # Model selection - allows per-feature model override
    model_override: Optional[str] = Field(
        default=None,
        description="Override model for this feature (e.g., 'claude-opus-4-5-20251101' for complex tasks)"
    )

    # Test verification steps (optional, for test-driven features)
    steps: list[str] = Field(
        default_factory=list,
        description="Step-by-step test verification steps for the feature"
    )

    # Source tracking - how this feature was created
    source: Optional[str] = Field(
        default=None,
        description="How this feature was created: 'manual', 'discovery', or 'generated'"
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

    # Session mode - SDK is default for better observability and control
    session_mode: SessionMode = Field(
        default=SessionMode.SDK,
        description="How to invoke Claude: 'cli' (direct CLI, uses subscription, more reliable) or 'sdk' (Agent SDK, uses API credits, better observability)"
    )

    # Model settings - default to Opus for maximum capability
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

    # Testing (legacy - prefer verification config)
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
    cli_read_timeout_seconds: int = Field(
        default=120,
        description="Per-chunk read timeout in seconds. If no output for this long, check if stuck."
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

    # Phase 3: Verification configuration
    verification: Optional["VerificationConfig"] = Field(
        default=None,
        description="Verification settings for Phase 3 quality gates"
    )


class UsageStats(BaseModel):
    """Token usage and cost statistics for a session or operation."""
    input_tokens: int = Field(default=0, description="Total input tokens consumed")
    output_tokens: int = Field(default=0, description="Total output tokens generated")
    cache_read_tokens: int = Field(default=0, description="Tokens read from cache")
    cache_write_tokens: int = Field(default=0, description="Tokens written to cache")
    model: str = Field(default="", description="Model used for this operation")
    cost_usd: float = Field(default=0.0, description="Estimated cost in USD")

    def __add__(self, other: "UsageStats") -> "UsageStats":
        """Add two UsageStats together."""
        return UsageStats(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            model=self.model or other.model,
            cost_usd=self.cost_usd + other.cost_usd
        )


class SessionOutcome(str, Enum):
    """Outcome of a completed session."""
    SUCCESS = "success"      # Feature completed successfully
    FAILURE = "failure"      # Session failed with error
    HANDOFF = "handoff"      # Session ended at context threshold
    TIMEOUT = "timeout"      # Session timed out


class SessionRecord(BaseModel):
    """Record of a completed session for history tracking.

    Stored in .ada_session_history.json for cost tracking and analytics.
    """
    session_id: str = Field(..., description="Unique session identifier")
    feature_id: Optional[str] = Field(default=None, description="Feature being worked on")
    started_at: datetime = Field(default_factory=datetime.now, description="Session start time")
    ended_at: Optional[datetime] = Field(default=None, description="Session end time")
    outcome: SessionOutcome = Field(default=SessionOutcome.SUCCESS, description="How the session ended")

    # Token usage
    input_tokens: int = Field(default=0, description="Total input tokens")
    output_tokens: int = Field(default=0, description="Total output tokens")
    cache_read_tokens: int = Field(default=0, description="Cache read tokens")
    cache_write_tokens: int = Field(default=0, description="Cache write tokens")

    # Cost tracking
    model: str = Field(default="", description="Model used")
    cost_usd: float = Field(default=0.0, description="Session cost in USD")

    # Work done
    files_changed: list[str] = Field(default_factory=list, description="Files modified")
    commit_hash: Optional[str] = Field(default=None, description="Commit hash if committed")

    # Error info
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    error_category: Optional[str] = Field(default=None, description="Error category")

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate session duration in seconds."""
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    def to_usage_stats(self) -> UsageStats:
        """Convert to UsageStats for aggregation."""
        return UsageStats(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens,
            model=self.model,
            cost_usd=self.cost_usd
        )


# =============================================================================
# Discovery Models (Phase 1.5)
# =============================================================================


class Severity(str, Enum):
    """Severity level for discovered issues."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueCategory(str, Enum):
    """Category of discovered code issues."""
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    CODE_SMELL = "code_smell"
    ERROR_HANDLING = "error_handling"
    VALIDATION = "validation"
    HARDCODED = "hardcoded"
    DEPRECATED = "deprecated"


class CodeIssue(BaseModel):
    """A single code issue discovered during analysis."""
    id: str = Field(..., description="Unique identifier for the issue")
    file: str = Field(..., description="File path where issue was found")
    line: Optional[int] = Field(default=None, description="Line number if applicable")
    severity: Severity = Field(default=Severity.MEDIUM)
    category: IssueCategory = Field(default=IssueCategory.CODE_SMELL)
    title: str = Field(..., description="Short title of the issue")
    description: str = Field(..., description="Detailed description of the issue")
    suggested_fix: Optional[str] = Field(
        default=None,
        description="Suggested fix or improvement"
    )


class TestGap(BaseModel):
    """A gap in test coverage."""
    id: str = Field(..., description="Unique identifier for the gap")
    module: str = Field(..., description="Module or file path missing tests")
    gap_type: Literal["no_tests", "partial_coverage", "missing_edge_cases"] = Field(
        default="no_tests",
        description="Type of test coverage gap"
    )
    severity: Severity = Field(default=Severity.MEDIUM)
    is_critical_path: bool = Field(
        default=False,
        description="Whether this is part of a critical code path"
    )
    description: Optional[str] = Field(
        default=None,
        description="Details about what tests are missing"
    )


class BestPracticeViolation(BaseModel):
    """A violation of coding best practices."""
    id: str = Field(..., description="Unique identifier for the violation")
    category: str = Field(..., description="Category of best practice (e.g., 'linting', 'typing')")
    severity: Severity = Field(default=Severity.LOW)
    title: str = Field(..., description="Short title of the violation")
    description: str = Field(..., description="What is missing or wrong")
    recommendation: str = Field(..., description="Recommended action to fix")


class ProjectSummary(BaseModel):
    """Summary of a project's structure and characteristics."""
    languages: list[str] = Field(
        default_factory=list,
        description="Programming languages detected"
    )
    frameworks: list[str] = Field(
        default_factory=list,
        description="Frameworks detected"
    )
    structure: dict[str, str] = Field(
        default_factory=dict,
        description="Directory structure mapping (path -> purpose)"
    )
    entry_points: list[str] = Field(
        default_factory=list,
        description="Main entry points of the application"
    )
    dependencies: dict[str, str] = Field(
        default_factory=dict,
        description="Dependencies and their versions"
    )
    line_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Line counts by category (code, tests, docs)"
    )


class DiscoveryResult(BaseModel):
    """Complete results of a discovery analysis."""
    project_path: str = Field(..., description="Path to the analyzed project")
    summary: ProjectSummary = Field(
        default_factory=ProjectSummary,
        description="Project summary"
    )
    code_issues: list[CodeIssue] = Field(
        default_factory=list,
        description="Code issues found"
    )
    test_gaps: list[TestGap] = Field(
        default_factory=list,
        description="Test coverage gaps found"
    )
    best_practice_violations: list[BestPracticeViolation] = Field(
        default_factory=list,
        description="Best practice violations found"
    )
    discovered_at: datetime = Field(
        default_factory=datetime.now,
        description="When the discovery was performed"
    )

    def total_issues(self) -> int:
        """Get total number of issues across all categories."""
        return (
            len(self.code_issues) +
            len(self.test_gaps) +
            len(self.best_practice_violations)
        )

    def issues_by_severity(self) -> dict[Severity, int]:
        """Count issues by severity."""
        counts: dict[Severity, int] = {s: 0 for s in Severity}
        for issue in self.code_issues:
            counts[issue.severity] += 1
        for gap in self.test_gaps:
            counts[gap.severity] += 1
        for violation in self.best_practice_violations:
            counts[violation.severity] += 1
        return counts


class DiscoveryState(BaseModel):
    """State for incremental discovery tracking."""
    project_path: str = Field(..., description="Path to the tracked project")
    known_issue_ids: list[str] = Field(
        default_factory=list,
        description="IDs of issues that have been seen"
    )
    resolved_issue_ids: list[str] = Field(
        default_factory=list,
        description="IDs of issues that have been resolved"
    )
    last_commit_hash: Optional[str] = Field(
        default=None,
        description="Commit hash when last discovery was run"
    )
    last_run_at: Optional[datetime] = Field(
        default=None,
        description="When the last discovery was run"
    )

    def is_known(self, issue_id: str) -> bool:
        """Check if an issue ID is already known."""
        return issue_id in self.known_issue_ids

    def is_resolved(self, issue_id: str) -> bool:
        """Check if an issue ID has been resolved."""
        return issue_id in self.resolved_issue_ids

    def mark_known(self, issue_id: str) -> None:
        """Mark an issue as known."""
        if issue_id not in self.known_issue_ids:
            self.known_issue_ids.append(issue_id)

    def mark_resolved(self, issue_id: str) -> None:
        """Mark an issue as resolved."""
        if issue_id not in self.resolved_issue_ids:
            self.resolved_issue_ids.append(issue_id)


# =============================================================================
# Verification Models (Phase 3)
# =============================================================================


class VerificationConfig(BaseModel):
    """Configuration for feature verification (Phase 3 quality gates).

    These settings control what validations run before a feature is marked complete.
    """
    # Test commands
    test_command: Optional[str] = Field(
        default="npm test",
        description="Unit test command to run (None to skip)"
    )
    e2e_command: Optional[str] = Field(
        default=None,
        description="E2E test command (e.g., 'npx playwright test')"
    )
    e2e_test_patterns: dict[str, str] = Field(
        default_factory=dict,
        description="Feature-specific E2E test patterns (feature_id -> grep pattern)"
    )

    # Lint and type checking
    lint_command: Optional[str] = Field(
        default=None,
        description="Lint command to run (e.g., 'npm run lint', 'ruff check .')"
    )
    type_check_command: Optional[str] = Field(
        default=None,
        description="Type check command (e.g., 'npm run typecheck', 'mypy .')"
    )

    # Coverage
    coverage_command: Optional[str] = Field(
        default=None,
        description="Command to run tests with coverage (e.g., 'npm run test:coverage')"
    )
    coverage_threshold: Optional[float] = Field(
        default=None,
        description="Minimum coverage percentage required (e.g., 80.0)"
    )
    coverage_report_path: Optional[str] = Field(
        default=None,
        description="Path to coverage report JSON (e.g., 'coverage/coverage-summary.json')"
    )

    # Hooks
    pre_complete_hook: Optional[str] = Field(
        default=None,
        description="Path to pre-complete hook script (default: .ada/hooks/pre-complete.sh)"
    )
    hooks_dir: str = Field(
        default=".ada/hooks",
        description="Directory for hook scripts"
    )

    # Visual regression
    visual_regression_enabled: bool = Field(
        default=False,
        description="Enable visual regression testing with Playwright"
    )
    baseline_screenshots_dir: str = Field(
        default=".ada/baselines",
        description="Directory for baseline screenshots"
    )
    screenshot_diff_threshold: float = Field(
        default=0.1,
        description="Maximum allowed pixel difference ratio (0.1 = 10%)"
    )

    # Manual approval
    require_manual_approval: bool = Field(
        default=False,
        description="Require human approval before marking feature complete"
    )
    approval_features: list[str] = Field(
        default_factory=list,
        description="Feature IDs that require manual approval (empty = use global setting)"
    )

    # Timeouts
    test_timeout_seconds: int = Field(
        default=300,
        description="Timeout for test commands (5 minutes default)"
    )
    e2e_timeout_seconds: int = Field(
        default=600,
        description="Timeout for E2E tests (10 minutes default)"
    )


class VerificationResult(BaseModel):
    """Result of a verification check."""
    name: str = Field(..., description="Name of the verification check")
    passed: bool = Field(..., description="Whether the check passed")
    message: str = Field(..., description="Human-readable result message")
    duration_seconds: Optional[float] = Field(
        default=None,
        description="How long the check took"
    )
    details: Optional[str] = Field(
        default=None,
        description="Detailed output or error message"
    )
    skipped: bool = Field(
        default=False,
        description="Whether the check was skipped"
    )


class CoverageReport(BaseModel):
    """Parsed coverage report data."""
    total_lines: int = Field(default=0, description="Total lines of code")
    covered_lines: int = Field(default=0, description="Lines covered by tests")
    coverage_percent: float = Field(default=0.0, description="Coverage percentage")
    uncovered_files: list[str] = Field(
        default_factory=list,
        description="Files with no coverage"
    )
    low_coverage_files: list[tuple[str, float]] = Field(
        default_factory=list,
        description="Files with coverage below threshold (file, percent)"
    )


class VerificationReport(BaseModel):
    """Complete verification report for a feature."""
    feature_id: str = Field(..., description="Feature being verified")
    passed: bool = Field(..., description="Whether all required checks passed")
    results: list[VerificationResult] = Field(
        default_factory=list,
        description="Individual check results"
    )
    coverage: Optional[CoverageReport] = Field(
        default=None,
        description="Coverage report if coverage check was run"
    )
    requires_approval: bool = Field(
        default=False,
        description="Whether manual approval is required"
    )
    approved: bool = Field(
        default=False,
        description="Whether manual approval was given"
    )
    approved_by: Optional[str] = Field(
        default=None,
        description="Who approved (if manual approval given)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When verification was run"
    )


# =============================================================================
# Alert Models (Phase 2 O9)
# =============================================================================


class AlertType(str, Enum):
    """Type of alert notification."""
    COST_THRESHOLD = "cost_threshold"
    SESSION_FAILED = "session_failed"
    FEATURE_BLOCKED = "feature_blocked"
    FEATURE_COMPLETED = "feature_completed"
    HANDOFF_OCCURRED = "handoff_occurred"


class AlertSeverity(str, Enum):
    """Severity level for alerts."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


# =============================================================================
# Observability Models (Session Logging)
# =============================================================================


class LogEntryType(str, Enum):
    """Types of log entries for session JSONL files."""
    SESSION_START = "session_start"
    PROMPT = "prompt"
    ASSISTANT = "assistant"
    TOOL_RESULT = "tool_result"
    CONTEXT_UPDATE = "context_update"
    ERROR = "error"
    SESSION_END = "session_end"


class ProjectContext(BaseModel):
    """Project metadata stored in .ada/project.json."""
    version: str = "1.0"
    name: str = Field(..., description="Project name")
    description: str = Field(default="", description="Project description")
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="user")

    context: dict = Field(
        default_factory=dict,
        description="Additional context (tech_stack, constraints, notes)"
    )
    init_session: Optional[dict] = Field(
        default=None,
        description="Info about the initializer session"
    )


class SessionIndexEntry(BaseModel):
    """Summary entry in the session index for fast lookup."""
    session_id: str = Field(..., description="Unique session identifier")
    file: str = Field(..., description="Relative path to the session log file")
    agent_type: str = Field(..., description="Type of agent: initializer or coding")
    feature_id: Optional[str] = Field(default=None, description="Feature being worked on")
    started_at: datetime = Field(default_factory=datetime.now)
    ended_at: Optional[datetime] = Field(default=None)
    outcome: Optional[str] = Field(default=None, description="success, failure, handoff, timeout")
    turns: int = Field(default=0, description="Number of agentic turns")
    tokens_total: int = Field(default=0, description="Total tokens used")
    cost_usd: float = Field(default=0.0, description="Session cost in USD")
    size_bytes: int = Field(default=0, description="Size of the log file")
    archived: bool = Field(default=False, description="Whether session is archived")
    archive_file: Optional[str] = Field(default=None, description="Archive file if archived")


class SessionIndex(BaseModel):
    """Index of all sessions for fast lookup without scanning log files."""
    version: str = "1.0"
    total_sessions: int = Field(default=0)
    total_size_bytes: int = Field(default=0)
    sessions: list[SessionIndexEntry] = Field(default_factory=list)

    def add_session(self, entry: SessionIndexEntry) -> None:
        """Add a session to the index."""
        self.sessions.append(entry)
        self.total_sessions = len(self.sessions)
        self.total_size_bytes += entry.size_bytes

    def get_session(self, session_id: str) -> Optional[SessionIndexEntry]:
        """Get a session by ID."""
        for session in self.sessions:
            if session.session_id == session_id:
                return session
        return None

    def update_session(self, session_id: str, **updates) -> bool:
        """Update a session entry."""
        for i, session in enumerate(self.sessions):
            if session.session_id == session_id:
                session_dict = session.model_dump()
                session_dict.update(updates)
                self.sessions[i] = SessionIndexEntry.model_validate(session_dict)
                # Recalculate total size
                self.total_size_bytes = sum(s.size_bytes for s in self.sessions)
                return True
        return False

    def get_recent_sessions(self, count: int = 10) -> list[SessionIndexEntry]:
        """Get the most recent sessions."""
        sorted_sessions = sorted(
            self.sessions,
            key=lambda s: s.started_at,
            reverse=True
        )
        return sorted_sessions[:count]

    def get_sessions_by_feature(self, feature_id: str) -> list[SessionIndexEntry]:
        """Get all sessions for a specific feature."""
        return [s for s in self.sessions if s.feature_id == feature_id]

    def get_sessions_by_outcome(self, outcome: str) -> list[SessionIndexEntry]:
        """Get all sessions with a specific outcome."""
        return [s for s in self.sessions if s.outcome == outcome]


class Alert(BaseModel):
    """An alert notification for the dashboard."""
    id: str = Field(..., description="Unique alert identifier")
    type: AlertType = Field(..., description="Type of alert")
    severity: AlertSeverity = Field(default=AlertSeverity.INFO, description="Alert severity")
    title: str = Field(..., description="Short alert title")
    message: str = Field(..., description="Detailed alert message")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the alert was created")
    read: bool = Field(default=False, description="Whether the alert has been read")
    dismissed: bool = Field(default=False, description="Whether the alert has been dismissed")
    feature_id: Optional[str] = Field(default=None, description="Related feature ID")
    session_id: Optional[str] = Field(default=None, description="Related session ID")
