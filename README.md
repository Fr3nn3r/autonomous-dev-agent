# Autonomous Development Agent (ADA)

A harness for running long-running autonomous coding agents using the Claude Agent SDK.

Based on [Anthropic's research](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) on effective harnesses for long-running agents.

## Concept

Traditional AI coding assistants hit context window limits during large tasks. ADA solves this by:

1. **Structured Backlog**: Features defined in JSON (not markdown) to prevent accidental corruption
2. **Progress Tracking**: `claude-progress.txt` gives each session immediate context
3. **Clean Handoffs**: At 70% context usage, commit changes and write handoff notes
4. **Continuous Loop**: New sessions pick up exactly where the last one stopped

## Installation

```bash
pip install -e .
```

Requires the Claude Agent SDK:
```bash
pip install claude-agent-sdk
```

## Quick Start

### 1. Initialize a project

```bash
ada init /path/to/project --name "My Project"
```

### 2. Add features to the backlog

```bash
ada add-feature /path/to/project \
  --name "User Authentication" \
  --description "Implement login and registration with JWT" \
  --priority 10 \
  --criteria "User can register" \
  --criteria "User can log in" \
  --criteria "Protected routes work"
```

Or manually edit `feature-list.json`:

```json
{
  "project_name": "My Project",
  "project_path": "/path/to/project",
  "features": [
    {
      "id": "user-auth",
      "name": "User Authentication",
      "description": "Implement login and registration with JWT",
      "category": "functional",
      "status": "pending",
      "priority": 10,
      "acceptance_criteria": [
        "User can register",
        "User can log in",
        "Protected routes work"
      ],
      "depends_on": []
    }
  ]
}
```

### 3. Run the agent

```bash
ada run /path/to/project
```

Options:
- `--model`: Claude model to use (default: claude-sonnet-4-20250514)
- `--threshold`: Context threshold % for handoff (default: 70)
- `--max-sessions`: Stop after N sessions (default: unlimited)

### 4. Monitor progress

```bash
# Show feature status
ada status /path/to/project

# Show recent progress
ada progress /path/to/project --lines 100
```

## How It Works

### Session Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    First Run (Initializer)                   │
│  1. Verify environment (pwd, git status)                    │
│  2. Create init.sh script                                   │
│  3. Initialize progress file                                │
│  4. Make initial commit                                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Coding Sessions (Loop)                    │
│  1. Read progress file for context                          │
│  2. Select next feature (priority + dependencies)           │
│  3. Run tests (baseline check)                              │
│  4. Implement feature incrementally                         │
│  5. At 70% context: commit + write handoff notes            │
│  6. Loop continues with fresh context                       │
└─────────────────────────────────────────────────────────────┘
```

### Key Artifacts

| File | Purpose |
|------|---------|
| `feature-list.json` | Structured backlog (JSON prevents LLM corruption) |
| `claude-progress.txt` | Append-only log of what each session did |
| `init.sh` | Script to start dev servers |
| `.ada_session_state.json` | Recovery state for interrupted sessions |

### Handoff Pattern

When context reaches 70%:

1. **Commit**: Stage and commit all changes with descriptive message
2. **Document**: Write to progress file what was done and what's next
3. **Clear**: End session, freeing context window
4. **Resume**: New session reads progress file, continues work

## Configuration

Create `.ada/config.json` in your project:

```json
{
  "context_threshold_percent": 70,
  "model": "claude-sonnet-4-20250514",
  "auto_commit": true,
  "run_tests_before_commit": true,
  "allowed_tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
}
```

## Custom Prompts

Override default prompts by creating `.ada/prompts/` in your project:

- `initializer.txt` - First-run environment setup
- `coding.txt` - Feature implementation sessions
- `handoff.txt` - Clean handoff procedure

## Import from Markdown

Convert existing markdown backlogs:

```bash
ada import-backlog /path/to/project BACKLOG.md
```

Parses task list format:
```markdown
- [ ] Feature name: Description
- [x] Completed feature: Already done
```

## Architecture

```
autonomous-dev-agent/
├── src/autonomous_dev_agent/
│   ├── models.py      # Pydantic models (Feature, Backlog, Config)
│   ├── harness.py     # Main orchestrator
│   ├── session.py     # Claude Agent SDK wrapper
│   ├── progress.py    # Progress file management
│   ├── git_manager.py # Git operations
│   ├── cli.py         # Click CLI
│   └── prompts/       # Default prompt templates
└── examples/
    └── feature-list.json
```

## Credits

Based on patterns from:
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
