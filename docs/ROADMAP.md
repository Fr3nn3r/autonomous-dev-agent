# ADA Roadmap

**Last Updated**: 2026-01-18
**Status**: Active Development
**Target**: Personal use, stability-focused

## Overview

This roadmap prioritizes reliability and observability over scalability. The goal is to make ADA robust enough for unattended operation on Windows before expanding capabilities.

**Priority Order**:
1. Reliability (make it work consistently)
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

## Phase 2: Observability (Dashboard)

**Goal**: Real-time visibility into agent progress and costs.

**Status**: 📋 Planned

**Tech Stack** (matching AgenticContextBuilder for consistency):
- Vite + React 18 + TypeScript
- Tailwind CSS with darkMode: 'class'
- shadcn/ui components
- Theming: Northern Lights (teal), Default (gray), Pink (rose) + Light/Dark mode
- @space-man/react-theme-animation for theme transitions

| ID | Feature | Description | Status | Priority |
|----|---------|-------------|--------|----------|
| O1 | **Cost Tracking** | Track tokens (input/output/cache), calculate API cost per session and per feature. Store in session results and backlog. | ⏳ Pending | Critical |
| O2 | **Dashboard Backend** | FastAPI server exposing ADA state via REST API. Endpoints: `/status`, `/backlog`, `/sessions`, `/progress`, `/config`. WebSocket for live updates. | ⏳ Pending | Critical |
| O3 | **Dashboard UI** | Real-time view: current feature, session progress, backlog status, recent activity. Match AgenticContextBuilder design. | ⏳ Pending | Critical |
| O4 | **Session History** | Persistent log of all sessions: start/end time, duration, tokens used, cost, outcome (success/failure/handoff), feature worked on. | ⏳ Pending | High |
| O5 | **Live Log Streaming** | WebSocket stream of progress file updates. Real-time console output in dashboard. | ⏳ Pending | High |
| O6 | **Feature Timeline** | Visual timeline/Gantt showing feature progression across sessions. Time spent per feature. | ⏳ Pending | Medium |
| O7 | **Cost Projections** | Estimate remaining cost based on: features pending, average cost per feature, historical data. | ⏳ Pending | Medium |
| O8 | **Alerts/Notifications** | Desktop notifications (Windows toast) on: completion, failure, billing warning. Optional email/webhook. | ⏳ Pending | Low |

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

---

## Phase 3: Verification (Quality Gates)

**Goal**: Ensure features actually work before marking complete.

**Status**: 📋 Planned

**Note**: Use Playwright CLI directly, not via MCP server.

| ID | Feature | Description | Status | Priority |
|----|---------|-------------|--------|----------|
| V1 | **Playwright CLI Integration** | Run Playwright tests via CLI for E2E validation. Configure test patterns per feature. `npx playwright test --grep "feature-name"` | ⏳ Pending | Critical |
| V2 | **Pre-Complete Hooks** | Run custom validation scripts before marking feature done. Configurable per-project in `.ada/hooks/pre-complete.sh`. | ⏳ Pending | High |
| V3 | **Visual Regression** | Screenshot comparison using Playwright. Store baseline screenshots, compare after implementation. Flag visual changes for review. | ⏳ Pending | High |
| V4 | **Test Coverage Check** | Verify new code has tests. Use coverage tools (nyc, coverage.py) to check coverage delta. Warn if coverage drops. | ⏳ Pending | Medium |
| V5 | **Lint/Type Check** | Run linters (ESLint, Ruff) and type checkers (TypeScript, mypy) as quality gates. Fail if errors introduced. | ⏳ Pending | Medium |
| V6 | **Manual Approval Mode** | Option to pause and require human approval before marking feature complete. Useful for critical features. | ⏳ Pending | Low |

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
- **Default**: claude-opus-4-5-20251101
- **Configurable**: Any Claude model via `--model` flag

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
| 0.4.0 | TBD | Phase 2 observability dashboard |
| 0.5.0 | TBD | Phase 3 verification features |
