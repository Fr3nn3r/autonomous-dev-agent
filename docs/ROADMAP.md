# ADA Roadmap

**Last Updated**: 2026-01-18
**Status**: Active Development
**Target**: Personal use, stability-focused

## Overview

This roadmap prioritizes reliability and observability over scalability. The goal is to make ADA robust enough for unattended operation on Windows before expanding capabilities.

**Priority Order**:
1. Reliability (make it work consistently) ✅
1.5. Discovery (analyze existing projects, generate backlog)
2. Observability (see what it's doing, track costs)
3. Verification (ensure quality before marking complete)
4. Scalability (handle larger projects - future)

---

## Phase 1: Reliability (Foundation)

**Goal**: Make ADA robust and trustworthy for unattended operation on Windows.

**Status**: ✅ Complete (2026-01-18)

| ID | Feature | Description | Status | Priority |
|----|---------|-------------|--------|----------|
| R1 | **Retry Logic** | Retry failed sessions with exponential backoff. Configurable max retries (default: 3). Distinguish between retryable errors (network, rate limit, SDK crash) and permanent errors (auth, billing). | ✅ Done | Critical |
| R2 | **Test Validation** | Run project tests before marking features complete. If tests fail, keep feature as in_progress and log the failure. Configurable test command per project. | ✅ Done | Critical |
| R3 | **Session Resume** | Save session checkpoints to `.ada_session_state.json`. On restart, offer to resume from last checkpoint or start fresh. Track partial progress within features. | ✅ Done | High |
| R4 | **Error Classification** | Classify errors into categories: `transient` (retry), `billing` (stop, notify), `auth` (stop, notify), `unknown` (retry with backoff). Already partially implemented for SDK errors. | ✅ Done | High |
| R5 | **Rollback Capability** | If tests fail after a session, offer to rollback to last known good commit. Use git reflog for safety. Never auto-rollback without confirmation in interactive mode. | ✅ Done | High |
| R6 | **Health Checks** | Pre-flight checks before starting: API connectivity, git clean status, disk space, required tools installed. Fail fast with clear error messages. | ✅ Done | Medium |
| R7 | **Graceful Shutdown** | Handle Ctrl+C (SIGINT) cleanly: commit current work, write handoff notes to progress file, save session state, exit cleanly. Partially implemented. | ✅ Done | Medium |
| R8 | **Session Timeout** | Configurable max duration per session (default: 30 minutes). Prevents runaway sessions. Triggers clean handoff when timeout approaches. | ✅ Done | Medium |

### Phase 1 Implementation Notes

**R1: Retry Logic**
```python
class RetryConfig:
    max_retries: int = 3
    base_delay_seconds: float = 5.0
    max_delay_seconds: float = 300.0  # 5 minutes
    exponential_base: float = 2.0
    retryable_errors: list[str] = ["transient", "rate_limit", "sdk_crash"]
```

**R2: Test Validation**
- Add `test_command` to HarnessConfig (e.g., "npm test", "pytest")
- Run tests after each session before marking feature complete
- If tests fail: keep feature as `in_progress`, increment `sessions_spent`, add failure note

**R4: Error Classification**
```python
class ErrorCategory(Enum):
    TRANSIENT = "transient"      # Network, timeout - retry
    RATE_LIMIT = "rate_limit"    # Too many requests - retry with longer delay
    SDK_CRASH = "sdk_crash"      # Windows exit code 1 - retry
    BILLING = "billing"          # Out of credits - stop
    AUTH = "auth"                # Invalid API key - stop
    UNKNOWN = "unknown"          # Unexpected - retry once, then stop
```

---

## Phase 1.5: Discovery (Brownfield Projects)

**Goal**: Enable ADA to work on existing/partially-implemented projects by analyzing the codebase and generating a backlog of remaining work.

**Status**: ✅ Complete (2026-01-18)

**Use Cases**:
- Project implemented but not tested
- Project started but abandoned
- Project needs code review and fixes
- Onboarding to unfamiliar codebase

| ID | Feature | Description | Status | Priority |
|----|---------|-------------|--------|----------|
| D1 | **Codebase Analysis** | Analyze project structure, tech stack, dependencies, file organization. Generate a project summary for agent context. | ✅ Done | Critical |
| D2 | **Code Review Agent** | Automated code review: identify bugs, security issues, code smells, missing error handling, inconsistent patterns. Generate issues list. | ✅ Done | Critical |
| D3 | **Test Gap Analysis** | Identify untested code, missing test files, low coverage areas. Map features to tests. Flag critical paths without tests. | ✅ Done | Critical |
| D4 | **Requirements Extraction** | Parse README, docs, comments, existing tests to understand intended functionality. Build a "definition of done" checklist. | ✅ Done | High |
| D5 | **Backlog Generation** | Convert gaps and issues into prioritized feature-list.json. Estimate effort, set priorities, detect dependencies automatically. | ✅ Done | High |
| D6 | **Diff from Ideal** | Compare current state against best practices (linting, typing, tests, docs, security). Generate remediation tasks. | ✅ Done | Medium |
| D7 | **Incremental Discovery** | Re-run discovery after each session to update remaining work. Track progress toward "done" state. | ✅ Done | Medium |

### Phase 1.5 Implementation Notes

**D1: Codebase Analysis**
```python
class CodebaseAnalyzer:
    """Analyze existing project structure."""

    def analyze(self, project_path: Path) -> ProjectSummary:
        """Generate comprehensive project analysis."""
        return ProjectSummary(
            tech_stack=self.detect_tech_stack(),      # Python, Node, etc.
            frameworks=self.detect_frameworks(),       # FastAPI, React, etc.
            structure=self.map_directory_structure(),  # Key folders/files
            entry_points=self.find_entry_points(),     # main.py, index.ts
            config_files=self.find_configs(),          # pyproject.toml, package.json
            dependencies=self.parse_dependencies(),    # From lockfiles
            line_count=self.count_lines_by_type(),     # Code vs test vs docs
        )

class ProjectSummary(BaseModel):
    """Summary for agent context."""
    tech_stack: list[str]
    frameworks: list[str]
    structure: dict[str, str]  # path -> description
    entry_points: list[str]
    config_files: list[str]
    dependencies: dict[str, str]
    line_count: dict[str, int]  # {"code": 5000, "test": 1200, "docs": 300}
```

**D2: Code Review Agent**
```python
class CodeReviewAgent:
    """Automated code review using Claude."""

    REVIEW_PROMPT = '''
    Review this codebase for:
    1. Bugs and logic errors
    2. Security vulnerabilities (OWASP Top 10)
    3. Error handling gaps
    4. Code smells and anti-patterns
    5. Missing input validation
    6. Hardcoded secrets/credentials
    7. Performance issues
    8. Inconsistent coding patterns

    Output as JSON with severity (critical/high/medium/low) and file locations.
    '''

    def review(self, files: list[Path]) -> list[CodeIssue]:
        """Review files and return issues."""
        pass

class CodeIssue(BaseModel):
    file: str
    line: Optional[int]
    severity: Literal["critical", "high", "medium", "low"]
    category: str  # bug, security, smell, etc.
    description: str
    suggested_fix: Optional[str]
```

**D5: Backlog Generation**
```python
class BacklogGenerator:
    """Generate feature-list.json from discovery results."""

    def generate(
        self,
        code_issues: list[CodeIssue],
        test_gaps: list[TestGap],
        requirements: list[Requirement],
    ) -> list[Feature]:
        """Convert all gaps into prioritized features."""
        features = []

        # Critical issues first
        for issue in code_issues:
            if issue.severity == "critical":
                features.append(Feature(
                    id=f"fix-{issue.category}-{len(features)}",
                    description=f"Fix {issue.severity} {issue.category}: {issue.description}",
                    priority="critical",
                    effort="small",
                    category="bugfix",
                ))

        # Then test coverage
        for gap in test_gaps:
            features.append(Feature(
                id=f"test-{gap.module}",
                description=f"Add tests for {gap.module}",
                priority="high" if gap.is_critical_path else "medium",
                effort="medium",
                category="testing",
            ))

        return self.prioritize(features)
```

**CLI Commands:**
```bash
# Run discovery on existing project
ada discover <path>

# Discovery with code review
ada discover <path> --review

# Discovery and immediately start fixing
ada discover <path> --fix

# Show what discovery found (dry run)
ada discover <path> --dry-run
```

---

## Phase 2: Observability (Dashboard)

**Goal**: Real-time visibility into agent progress and costs.

**Status**: ✅ Complete (2026-01-18)

**Tech Stack** (matching AgenticContextBuilder for consistency):
- Vite + React 18 + TypeScript
- Tailwind CSS with darkMode: 'class'
- shadcn/ui components
- Theming: Northern Lights (teal), Default (gray), Pink (rose) + Light/Dark mode
- @space-man/react-theme-animation for theme transitions

| ID | Feature | Description | Status | Priority |
|----|---------|-------------|--------|----------|
| O1 | **Cost Tracking** | Track tokens (input/output/cache), calculate API cost per session and per feature. Parse CLI mode JSONL logs from `~/.claude/projects/`. Store costs in session results and backlog. Support both CLI and SDK modes. | ✅ Done | Critical |
| O2 | **Adaptive Model Selection** | Default to Sonnet for most tasks, use Opus only for complex features. Per-feature model override in backlog. Complexity detection based on feature description, estimated effort, and dependencies. | ✅ Done | Critical |
| O3 | **Dashboard Backend** | FastAPI server exposing ADA state via REST API. Endpoints: `/status`, `/backlog`, `/sessions`, `/progress`, `/config`. WebSocket for live updates. | ✅ Done | Critical |
| O4 | **Dashboard UI** | Real-time view: current feature, session progress, backlog status, recent activity. Match AgenticContextBuilder design. | ✅ Done | Critical |
| O5 | **Session History** | Persistent log of all sessions: start/end time, duration, tokens used, cost, outcome (success/failure/handoff), feature worked on. | ✅ Done | High |
| O6 | **Live Log Streaming** | WebSocket stream of progress file updates. Real-time console output in dashboard. | ✅ Done | High |
| O7 | **Feature Timeline** | Visual timeline/Gantt showing feature progression across sessions. Time spent per feature. | ✅ Done | Medium |
| O8 | **Cost Projections** | Estimate remaining cost based on: features pending, average cost per feature, historical data. | ✅ Done | Medium |
| O9 | **Alerts/Notifications** | Desktop notifications (Windows toast) on: completion, failure, billing warning. Optional email/webhook. | ✅ Done | Low |

### Phase 2 Dashboard Structure

```
ada-dashboard/
├── src/
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx
│   │   │   ├── Header.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── backlog/
│   │   │   ├── BacklogTable.tsx
│   │   │   ├── FeatureCard.tsx
│   │   │   └── FeatureTimeline.tsx
│   │   ├── session/
│   │   │   ├── CurrentSession.tsx
│   │   │   ├── SessionHistory.tsx
│   │   │   └── SessionDetails.tsx
│   │   ├── metrics/
│   │   │   ├── CostTracker.tsx
│   │   │   ├── TokenUsage.tsx
│   │   │   └── ProgressStats.tsx
│   │   └── ui/  # shadcn components
│   ├── lib/
│   │   ├── api-client.ts
│   │   ├── theme-context.tsx
│   │   ├── websocket.ts
│   │   └── utils.ts
│   └── App.tsx
├── package.json
└── vite.config.ts
```

### Phase 2 Implementation Notes

**O1: Cost Tracking**

Unified cost tracking for both CLI and SDK modes:

```python
class CostTracker:
    """Track and calculate costs from Claude usage."""

    # Pricing per 1M tokens (as of 2026-01)
    PRICING = {
        "claude-opus-4-5-20251101": {"input": 15.00, "output": 75.00, "cache_read": 1.50},
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
        "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00, "cache_read": 0.10},
    }

    def parse_cli_logs(self, project_path: Path) -> UsageStats:
        """Parse JSONL logs from ~/.claude/projects/<project>/"""
        # CLI mode stores usage in JSONL files with message.usage
        pass

    def get_sdk_usage(self, session_result: SessionResult) -> UsageStats:
        """Extract usage from SDK session result."""
        # SDK mode returns usage directly in message.usage
        pass

    def calculate_cost(self, stats: UsageStats, model: str) -> float:
        """Calculate cost in USD from token counts."""
        pass

class UsageStats(BaseModel):
    """Token usage statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0
    model: str = ""
    session_id: str = ""
    feature_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    cost_usd: float = 0.0
```

**O2: Adaptive Model Selection**

Default to Sonnet, escalate to Opus for complex tasks:

```python
class ModelSelector:
    """Select appropriate model based on task complexity."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    COMPLEX_MODEL = "claude-opus-4-5-20251101"

    # Complexity indicators that trigger Opus
    COMPLEXITY_KEYWORDS = [
        "architecture", "refactor", "security", "performance",
        "database", "migration", "integration", "api design"
    ]

    def select_model(self, feature: Feature) -> str:
        """Choose model based on feature complexity."""
        # 1. Check for explicit model override in feature
        if feature.model_override:
            return feature.model_override

        # 2. Check complexity based on effort estimate
        if feature.effort in ["large", "epic"]:
            return self.COMPLEX_MODEL

        # 3. Check for complexity keywords in description
        desc_lower = feature.description.lower()
        if any(kw in desc_lower for kw in self.COMPLEXITY_KEYWORDS):
            return self.COMPLEX_MODEL

        # 4. Check dependency count (many deps = complex)
        if len(feature.depends_on) >= 3:
            return self.COMPLEX_MODEL

        return self.DEFAULT_MODEL

# Feature model with optional override
class Feature(BaseModel):
    id: str
    description: str
    effort: Literal["small", "medium", "large", "epic"] = "medium"
    model_override: Optional[str] = None  # Force specific model
    # ... other fields
```

**CLI flag for model selection:**
```bash
# Use default adaptive selection
ada run <path>

# Force specific model for all features
ada run <path> --model claude-sonnet-4-20250514

# Force Opus for current session only
ada run <path> --model claude-opus-4-5-20251101
```

---

## Phase 3: Verification (Quality Gates)

**Goal**: Ensure features actually work before marking complete.

**Status**: ✅ Complete (2026-01-18)

**Note**: Use Playwright CLI directly, not via MCP server.

| ID | Feature | Description | Status | Priority |
|----|---------|-------------|--------|----------|
| V1 | **Playwright CLI Integration** | Run Playwright tests via CLI for E2E validation. Configure test patterns per feature. `npx playwright test --grep "feature-name"` | ✅ Done | Critical |
| V2 | **Pre-Complete Hooks** | Run custom validation scripts before marking feature done. Configurable per-project in `.ada/hooks/pre-complete.sh`. | ✅ Done | High |
| V3 | **Visual Regression** | Screenshot comparison using Playwright. Store baseline screenshots, compare after implementation. Flag visual changes for review. | ⏳ Pending | High |
| V4 | **Test Coverage Check** | Verify new code has tests. Use coverage tools (nyc, coverage.py) to check coverage delta. Warn if coverage drops. | ✅ Done | Medium |
| V5 | **Lint/Type Check** | Run linters (ESLint, Ruff) and type checkers (TypeScript, mypy) as quality gates. Fail if errors introduced. | ✅ Done | Medium |
| V6 | **Manual Approval Mode** | Option to pause and require human approval before marking feature complete. Useful for critical features. | ✅ Done | Low |

### Playwright Integration Design

```python
class VerificationConfig(BaseModel):
    """Verification settings per project."""
    test_command: str = "npm test"
    e2e_command: str = "npx playwright test"
    lint_command: Optional[str] = "npm run lint"
    type_check_command: Optional[str] = "npm run typecheck"
    coverage_threshold: Optional[float] = None  # e.g., 80.0
    require_manual_approval: bool = False

    # Feature-specific test patterns
    feature_test_patterns: dict[str, str] = {}
    # e.g., {"user-auth": "--grep 'auth|login'"}
```

---

## Phase 4: Scalability (Future)

**Goal**: Handle larger projects and parallel work.

**Status**: 📋 Future (Low Priority)

| ID | Feature | Description | Status | Priority |
|----|---------|-------------|--------|----------|
| S1 | **Subagents** | Spawn child agents for independent features. Coordinate via shared progress file. Merge results. | ⏳ Future | Medium |
| S2 | **Multi-Project** | Manage multiple projects from single harness. Project switching, aggregate dashboard. | ⏳ Future | Low |
| S3 | **Semantic Search** | Vector retrieval (embeddings) for large codebases. Help agent find relevant code faster. | ⏳ Future | Low |
| S4 | **Git Worktree Support** | Use git worktrees for parallel feature branches. Each subagent works in isolated worktree. | ⏳ Future | Low |

---

## GitHub Integration (Optional - Not Prioritized)

These features are available if needed later:

| Feature | Benefit | Implementation |
|---------|---------|----------------|
| Auto PR Creation | Each completed feature creates a PR | `gh pr create` after feature completion |
| Issue Linking | Link features to GitHub issues | Add `github_issue` field to Feature model |
| Status Checks | GitHub Actions runs tests on each commit | `.github/workflows/test.yml` |
| Code Review Workflow | Request reviews, merge when approved | `gh pr merge --auto` |
| Release Automation | Auto-create releases when milestones complete | `gh release create` |

---

## Technical Decisions

### Platform
- **Primary**: Windows 10/11
- **Secondary**: Cross-platform compatibility maintained but not primary focus

### Session Mode
- **Default**: CLI mode (uses Claude subscription, more reliable on Windows)
- **Alternative**: SDK mode (uses API credits, has Windows bugs)

### Model
- **Default**: claude-sonnet-4-20250514 (cost-effective for most tasks)
- **Complex tasks**: claude-opus-4-5-20251101 (auto-selected based on feature complexity)
- **Configurable**: Any Claude model via `--model` flag or per-feature `model_override`

### Architecture
- **Monorepo**: Single repo for harness + dashboard
- **Backend**: Python (existing) + FastAPI (new for dashboard API)
- **Frontend**: Vite + React + TypeScript (separate from harness)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-01-17 | Initial implementation: CLI, backlog, progress tracking |
| 0.2.0 | 2026-01-18 | Dual mode (CLI/SDK), verbose logging, Windows fixes |
| 0.3.0 | 2026-01-18 | Phase 1 reliability features (retry, test validation, resume, error classification, rollback, health checks, graceful shutdown, timeout) |
| 0.4.0 | 2026-01-18 | Phase 1.5 discovery (codebase analysis, code review, test gaps, requirements extraction, backlog generation, best practices, incremental tracking) + Phase 2 observability dashboard (cost tracking, model selection, session history, FastAPI backend, React UI) |
| 0.5.0 | 2026-01-18 | Phase 3 verification features (Playwright E2E, pre-complete hooks, coverage checking, lint/type checks, manual approval) |
| 0.6.0 | 2026-01-18 | Phase 2 completion: Feature timeline (Gantt view), cost projections, alerts/notifications with desktop notifications |
| 0.7.0 | TBD | Visual regression testing |
