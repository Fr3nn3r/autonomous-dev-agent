# Design Documentation

This document explains the architectural decisions and research behind the Autonomous Development Agent (ADA) harness.

## Sources & Research

This project is based on Anthropic's published research on building effective long-running agents:

### Primary Sources

1. **[Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)**
   - The core pattern: two-agent architecture (initializer + coding agent)
   - Why compaction alone isn't sufficient
   - The `claude-progress.txt` pattern for session handoffs
   - JSON format for backlogs (prevents LLM corruption)

2. **[Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)**
   - Agent feedback loop: Gather Context → Take Action → Verify Work
   - Context management strategies (agentic search, subagents, compaction)
   - Tools, bash scripts, and MCPs
   - Verification patterns (rules-based, visual, LLM-as-judge)

3. **[Claude Agent SDK Documentation](https://platform.claude.com/docs/en/agent-sdk/overview)**
   - SDK API reference
   - Session management and resumption
   - Token tracking
   - Hooks for lifecycle events

### Key Insights from Research

#### The Problem

> "Out of the box, even a frontier coding model like Opus 4.5 running on the Claude Agent SDK in a loop across multiple context windows will fall short of building a production-quality web app with only a high-level prompt. The agent tended to try to do too much at once, often running out of context mid-implementation, leaving the next session to start with half-implemented and undocumented features."

#### The Solution

> "A two-fold solution: an initializer agent that sets up the environment on the first run, and a coding agent that makes incremental progress in every session while leaving clear artifacts for the next session."

#### Why JSON for Backlogs

> "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality" - use JSON format (models less likely to corrupt than Markdown).

## Architecture Decisions

### 1. Two-Agent Pattern

**Decision**: Separate initializer agent from coding agent.

**Rationale**: The initializer runs once to set up:
- Git repository state
- Development environment (init.sh)
- Progress tracking file
- Initial commit

Subsequent coding sessions focus purely on implementation, reading from established artifacts.

### 2. JSON Backlog Format

**Decision**: Store features in `feature-list.json`, not markdown.

**Rationale**:
- LLMs are less likely to accidentally corrupt JSON structure
- Pydantic validation ensures data integrity
- Machine-readable for harness logic (dependency resolution, priority sorting)
- Human-editable when needed

**Structure**:
```json
{
  "id": "feature-id",
  "name": "Human readable name",
  "description": "What to implement",
  "status": "pending|in_progress|completed|blocked",
  "priority": 10,
  "acceptance_criteria": ["Criterion 1", "Criterion 2"],
  "depends_on": ["other-feature-id"]
}
```

### 3. Progress File Pattern

**Decision**: Append-only `claude-progress.txt` for session context.

**Rationale**:
- Each session reads this first to understand current state
- Append-only prevents data loss
- Human-readable for debugging
- Cheaper than loading full git history into context

**Format**:
```
============================================================
[2024-01-15 10:30:00] Session: s001_103000
Action: session_started
Feature: user-auth

Starting work on feature: User Authentication
...
```

### 4. Context Threshold Handoff

**Decision**: Trigger handoff at 70% context usage.

**Rationale**:
- Leaves 30% buffer for handoff operations (commit, write notes)
- Prevents context exhaustion mid-operation
- Configurable per project needs

**Handoff sequence**:
1. Commit all changes with descriptive message
2. Write detailed handoff notes to progress file
3. Update backlog with session notes
4. End session cleanly

### 5. Dependency Resolution

**Decision**: Features can declare dependencies; harness respects them.

**Rationale**:
- Prevents agents from starting features before prerequisites complete
- Natural ordering for complex projects
- In-progress features take priority over pending (continuity)

**Algorithm**:
```python
def get_next_feature():
    completed_ids = {f.id for f in features if f.completed}
    candidates = [f for f in features
                  if f.status in (PENDING, IN_PROGRESS)
                  and all(dep in completed_ids for dep in f.depends_on)]
    # Sort: in_progress first, then by priority (descending)
    return sorted(candidates, key=lambda f: (f.status != IN_PROGRESS, -f.priority))[0]
```

### 6. Git Integration

**Decision**: Auto-commit on handoff with structured messages.

**Rationale**:
- Every handoff creates a recoverable checkpoint
- Git history supplements progress file
- Enables rollback if session introduces bugs
- Commit messages document what changed and why

### 7. Prompt Templates

**Decision**: External prompt files, overridable per-project.

**Rationale**:
- Easy to tune without code changes
- Projects can customize for their stack/conventions
- Version controlled separately from harness logic

**Lookup order**:
1. `.ada/prompts/{name}.txt` (project-local)
2. `src/autonomous_dev_agent/prompts/{name}.txt` (package default)

## Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `models.py` | Data structures (Feature, Backlog, Config) with Pydantic validation |
| `harness.py` | Main orchestration loop, session coordination |
| `session.py` | Claude Agent SDK wrapper, context monitoring |
| `progress.py` | Progress file read/write, handoff logging |
| `git_manager.py` | Git operations (status, commit, diff) |
| `cli.py` | User interface (init, run, status, add-feature) |

## Session Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         HARNESS START                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Load Backlog   │
                    │  (JSON file)    │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Progress exists?│
                    └─────────────────┘
                         │       │
                    No   │       │  Yes
                         ▼       ▼
              ┌──────────────┐  ┌──────────────┐
              │ Run          │  │ Skip to      │
              │ Initializer  │  │ Coding Loop  │
              └──────────────┘  └──────────────┘
                         │       │
                         └───┬───┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CODING LOOP                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  1. Get next feature (priority + dependencies)          │   │
│  │  2. Read progress file for context                      │   │
│  │  3. Run coding session with feature prompt              │   │
│  │  4. Monitor context usage                               │   │
│  │  5. If threshold reached: handoff                       │   │
│  │  6. If feature complete: mark done, save backlog        │   │
│  │  7. Loop until backlog complete or max sessions         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Print Summary  │
                    │  (sessions,     │
                    │   completed)    │
                    └─────────────────┘
```

## Future Considerations

Based on the research, these enhancements could be valuable:

1. **Subagents for parallelization**: Independent features could run in parallel with isolated contexts
2. **Visual verification**: Screenshot comparison for UI features
3. **Browser automation**: Puppeteer MCP for end-to-end testing
4. **Semantic search**: Vector retrieval for large codebases
5. **Hooks**: Pre/post tool execution hooks for custom validation
6. **Token tracking**: Detailed token consumption reporting per session and feature

## References

- Anthropic Engineering Blog: https://www.anthropic.com/engineering
- Claude Agent SDK Docs: https://platform.claude.com/docs/en/agent-sdk
- Model Context Protocol: https://modelcontextprotocol.io
