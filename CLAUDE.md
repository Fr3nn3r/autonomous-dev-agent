# Autonomous Dev Agent (ADA)

Python harness for long-running autonomous coding agents. Solves context window limits via structured JSON backlogs and session handoffs.

## Stack
Python 3.10+ / Claude Agent SDK / Pydantic / Click / Rich

## Architecture

Two-agent pattern based on Anthropic research:
1. **Initializer** (one-time): Verify environment, create init.sh, initial commit
2. **Coding Agent** (loop): Implement features, handoff at 70% context

```
feature-list.json       # Structured backlog (JSON prevents LLM corruption)
claude-progress.txt     # Append-only session log for context handoffs
init.sh                 # Dev server startup script (agent-generated)
.ada_session_state.json # Recovery state (gitignored)
```

## Git Worktrees (Multi-Agent Development)

This repo supports **git worktrees** for parallel agent work.

```
C:\Users\fbrun\Documents\GitHub\
├── autonomous-dev-agent/       # PRIMARY - main branch
├── autonomous-dev-agent-wt1/   # Worktree slot 1
├── autonomous-dev-agent-wt2/   # Worktree slot 2
└── autonomous-dev-agent-wt3/   # Worktree slot 3
```

**Agent checklist at session start:**
1. Verify your working directory: `pwd && git branch --show-current`
2. Check for uncommitted changes: `git status`
3. Sync with main if needed: `git fetch origin && git rebase origin/main`

**Key rules:**
- Always confirm you're in the correct worktree before making changes
- Do NOT merge to main without user approval
- Do NOT switch worktrees without user permission
- Commit frequently with descriptive messages

## Commands
```bash
# Installation
pip install -e .                    # Editable install
pip install -e ".[dev]"             # With dev dependencies

# CLI (after install)
ada init <path>                     # Initialize new project
ada init <path> --spec spec.md      # Initialize with AI-generated features
ada run <path>                      # Execute agent harness
ada run <path> --model claude-sonnet-4-20250514 --threshold 70
ada add-feature <path>              # Add task to backlog
ada status <path>                   # Show backlog with colors
ada progress <path>                 # Display recent progress logs
ada import-backlog <path> <md>      # Convert markdown tasks to JSON
ada generate-backlog <spec>         # Generate features from spec file

# Tests
pytest tests/                       # Full suite
pytest tests/test_models.py -v      # Specific file
pytest -k "backlog" --tb=short      # By keyword
```

## Conventions
- Python: snake_case | Classes: PascalCase
- Type hints on all functions (Python 3.10+ syntax)
- Pydantic models for all data structures
- Test new/changed logic with PyTest
- Do not start/stop dev servers automatically - ask user first

## Versioning & Commits

**Current version**: Check `pyproject.toml`

### Semantic Versioning (MAJOR.MINOR.PATCH)
| Bump | When | Examples |
|------|------|----------|
| PATCH | Bug fixes, no API changes | Fix session bug, CLI typo |
| MINOR | New features, backward-compatible | New CLI command, new config option |
| MAJOR | Breaking changes | Backlog format change, config schema change |

### Commit Message Prefixes
- `fix:` - Bug fix (triggers PATCH bump)
- `feat:` - New feature (triggers MINOR bump)
- `BREAKING CHANGE:` - Breaking change (triggers MAJOR bump)
- `chore:` - Maintenance, deps, configs (no version bump)
- `docs:` - Documentation only (no version bump)
- `refactor:` - Code restructure, no behavior change (no version bump)
- `test:` - Adding/updating tests (no version bump)

## Testing Best Practices
- **Use `-v` for verbose output** when debugging specific tests
- **Use `--tb=short`** for concise error output
- **Use `-k` for keyword filtering**: `pytest -k "feature" --tb=short`
- Tests use pytest-asyncio for async support

## Context Management
- **docs/DESIGN.md** - Architecture decisions and rationale
- **docs/SOURCES.md** - Research sources from Anthropic
- **examples/feature-list.json** - Annotated backlog example
- Before `/clear`: Add handoff notes to progress file or backlog

## Key Paths
- Core: `src/autonomous_dev_agent/` (harness.py, session.py, models.py)
- Prompts: `src/autonomous_dev_agent/prompts/` (*.md files)
- Generation: `src/autonomous_dev_agent/generation/` (AI-driven backlog generation)
- Tests: `tests/` (test_models.py)
- Docs: `docs/` (DESIGN.md, SOURCES.md)

## Prompt System

Prompts are stored as `.md` files in `src/autonomous_dev_agent/prompts/` for editor syntax highlighting. Each serves a distinct purpose in the workflow:

| Prompt | Purpose | When Used |
|--------|---------|-----------|
| `initializer.md` | Sets up project workspace (git, init.sh, initial commit) | First `ada run` on new project |
| `coding.md` | Main development prompt for implementing features | Each coding session |
| `handoff.md` | Context transfer between sessions at threshold | When context reaches 70% |
| `generate_backlog.md` | One-shot Claude call to generate features from spec | `ada generate-backlog` or `ada init --spec` |
| `discovery_review.md` | AI code review for bugs/security issues | `ada discover` command |
| `discovery_requirements.md` | Extract requirements from documentation | `ada discover` command |

**Workflow sequence:**
1. **(Optional)** Generate backlog from spec → `generate_backlog.md`
2. Initialize workspace → `initializer.md`
3. Implement features → `coding.md` (loops)
4. At context threshold → `handoff.md` → back to step 3

**Custom prompts**: Place in `.ada/prompts/{name}.md` to override package defaults.

## Feature Scoping Best Practices

When generating backlogs (via `ada generate-backlog` or `ada init --spec`), feature count parameters (`--min-features`, `--max-features`) are **guidelines, not targets**. Prioritize proper scoping over hitting a specific number.

**Well-scoped features:**
- Complete, demoable units of functionality (not just code changes)
- Completable in one coding session (30-60 min agent work)
- 3-6 acceptance criteria

**Avoid fragmentation:**
- Don't separate UI from its API endpoint
- Don't create individual features for similar controls (e.g., multiple sliders → one "Parameter Controls" feature)
- Don't split tightly-coupled config (e.g., CSS variables + Tailwind config + theme provider → one "Theme System" feature)

**When to split:** Only when features can genuinely be delivered/tested independently and have different priorities.

See `src/autonomous_dev_agent/prompts/generate_backlog.md` for full scoping guidelines.

## Configuration

**HarnessConfig** options (models.py):
```python
context_threshold_percent: float = 70.0    # Trigger handoff
model: str = "claude-sonnet-4-20250514"    # Claude model
progress_file: str = "claude-progress.txt"
backlog_file: str = "feature-list.json"
auto_commit: bool = True
run_tests_before_commit: bool = True
```
