# ADA Observability Workspace Specification

## Overview

A structured `.ada/` workspace that captures all execution data for debugging, analysis, and system improvement.

**Design Principles:**
- Capture everything (verbose by default)
- JSON for structured queries and tooling
- Real-time streaming support
- Automatic rotation at 100MB
- Preserve initial project context

---

## Directory Structure

```
project-root/
├── feature-list.json           # Backlog (unchanged)
├── claude-progress.txt         # Human-readable summary (unchanged)
└── .ada/
    ├── project.json            # Project metadata + initial description
    ├── config.json             # Harness configuration overrides
    ├── logs/
    │   ├── sessions/
    │   │   ├── 20240115_001_initializer.jsonl
    │   │   ├── 20240115_002_coding_user-auth.jsonl
    │   │   └── 20240115_003_coding_user-auth.jsonl
    │   ├── index.json          # Session index for fast lookup
    │   └── current.jsonl       # Symlink/copy of active session
    ├── state/
    │   ├── session.json        # Current session state (moved from root)
    │   └── history.json        # Session history (moved from root)
    ├── alerts.json             # Alerts (moved from root)
    ├── prompts/                # Custom prompt overrides (exists)
    ├── hooks/                  # Validation hooks (exists)
    └── baselines/              # Visual regression (exists)
```

---

## 1. Project Context (`project.json`)

Captures initial project description and metadata that persists across sessions.

### Schema

```json
{
  "version": "1.0",
  "name": "My Application",
  "description": "A task management app that allows users to create, organize, and track tasks with support for recurring items, tags, and collaborative workspaces.",
  "created_at": "2024-01-15T10:00:00Z",
  "created_by": "user",

  "context": {
    "tech_stack": [],
    "constraints": [],
    "notes": ""
  },

  "init_session": {
    "session_id": "20240115_001",
    "prompt": "Full initializer prompt that was sent...",
    "outcome": "success"
  }
}
```

### CLI Changes

```bash
# Enhanced init command
ada init <path> --name "My App" --description "A task management app that..."

# Or interactive
ada init <path>
# Prompts for: name, description

# View project info
ada info <path>
```

---

## 2. Session Logs (`logs/sessions/*.jsonl`)

JSON Lines format - one JSON object per line for streaming and easy parsing.

### Naming Convention

```
{YYYYMMDD}_{NNN}_{agent_type}_{feature_id}.jsonl

Examples:
20240115_001_initializer.jsonl
20240115_002_coding_user-auth.jsonl
20240115_003_coding_user-auth.jsonl  # Handoff continuation
```

### Log Entry Types

Each line is a JSON object with a `type` field:

#### Session Start
```json
{
  "type": "session_start",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "session_id": "20240115_002",
  "agent_type": "coding",
  "feature_id": "user-auth",
  "feature_name": "User Authentication",
  "model": "claude-sonnet-4-20250514",
  "config": {
    "context_threshold_percent": 70,
    "session_mode": "cli",
    "max_turns": 100
  }
}
```

#### Prompt Sent
```json
{
  "type": "prompt",
  "timestamp": "2024-01-15T10:30:00.456Z",
  "prompt_name": "coding",
  "prompt_length": 4523,
  "prompt_text": "You are an autonomous coding agent...",
  "variables": {
    "feature_name": "User Authentication",
    "feature_description": "Implement login...",
    "acceptance_criteria": ["User can register...", "..."]
  }
}
```

#### Assistant Message
```json
{
  "type": "assistant",
  "timestamp": "2024-01-15T10:30:05.789Z",
  "turn": 1,
  "content": "I'll start by examining the current project structure...",
  "thinking": null,
  "tool_calls": [
    {
      "id": "call_001",
      "tool": "Glob",
      "input": {"pattern": "**/*.py"}
    }
  ]
}
```

#### Tool Result
```json
{
  "type": "tool_result",
  "timestamp": "2024-01-15T10:30:06.123Z",
  "turn": 1,
  "tool_call_id": "call_001",
  "tool": "Glob",
  "input": {"pattern": "**/*.py"},
  "output": "src/main.py\nsrc/models.py\nsrc/auth/__init__.py",
  "output_length": 156,
  "duration_ms": 45,
  "truncated": false
}
```

#### Tool Use (for tools like Edit, Write, Bash)
```json
{
  "type": "tool_result",
  "timestamp": "2024-01-15T10:30:10.456Z",
  "turn": 2,
  "tool_call_id": "call_002",
  "tool": "Edit",
  "input": {
    "file_path": "/path/to/auth/routes.py",
    "old_string": "def login():",
    "new_string": "def login(credentials: LoginRequest):"
  },
  "output": "Edit successful",
  "duration_ms": 12,
  "file_changed": "/path/to/auth/routes.py"
}
```

#### Error
```json
{
  "type": "error",
  "timestamp": "2024-01-15T10:35:00.000Z",
  "turn": 5,
  "category": "rate_limit",
  "message": "Rate limit exceeded",
  "raw_error": "anthropic.RateLimitError: ...",
  "recoverable": true
}
```

#### Context Update
```json
{
  "type": "context_update",
  "timestamp": "2024-01-15T10:35:30.000Z",
  "turn": 10,
  "input_tokens": 45000,
  "output_tokens": 12000,
  "total_tokens": 57000,
  "context_percent": 68.5,
  "cost_usd": 0.42
}
```

#### Session End
```json
{
  "type": "session_end",
  "timestamp": "2024-01-15T10:45:00.000Z",
  "session_id": "20240115_002",
  "outcome": "handoff",
  "reason": "Context threshold reached (72%)",
  "duration_seconds": 900,
  "turns": 15,
  "tokens": {
    "input": 52000,
    "output": 15000,
    "cache_read": 8000,
    "cache_write": 2000
  },
  "cost_usd": 0.58,
  "files_changed": [
    "src/auth/routes.py",
    "src/auth/models.py",
    "tests/test_auth.py"
  ],
  "commit_hash": "abc123f",
  "handoff_notes": "Completed login endpoint, next: implement logout..."
}
```

---

## 3. Session Index (`logs/index.json`)

Fast lookup without scanning all log files.

```json
{
  "version": "1.0",
  "total_sessions": 45,
  "total_size_bytes": 52428800,
  "sessions": [
    {
      "session_id": "20240115_002",
      "file": "sessions/20240115_002_coding_user-auth.jsonl",
      "agent_type": "coding",
      "feature_id": "user-auth",
      "started_at": "2024-01-15T10:30:00Z",
      "ended_at": "2024-01-15T10:45:00Z",
      "outcome": "handoff",
      "turns": 15,
      "tokens_total": 67000,
      "cost_usd": 0.58,
      "size_bytes": 125000
    }
  ]
}
```

---

## 4. Log Rotation

### Trigger
- When `logs/` directory exceeds 100MB total

### Strategy
1. Archive oldest sessions to `logs/archive/YYYYMM.tar.gz`
2. Keep last 50 sessions in `logs/sessions/`
3. Update `index.json` with archive references

### Archive Reference in Index
```json
{
  "session_id": "20231201_001",
  "archived": true,
  "archive_file": "archive/202312.tar.gz"
}
```

---

## 5. Real-Time Streaming

### Implementation

The active session writes to `logs/current.jsonl` (or symlink on Unix).

```python
class SessionLogger:
    def __init__(self, session_id: str, logs_dir: Path):
        self.log_file = logs_dir / "sessions" / f"{session_id}.jsonl"
        self.current_link = logs_dir / "current.jsonl"

    def log(self, entry: dict):
        """Append entry and flush immediately for real-time streaming."""
        entry["timestamp"] = datetime.now().isoformat()
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()
            os.fsync(f.fileno())  # Ensure written to disk
```

### CLI Streaming

```bash
# Follow current session in real-time
ada logs --tail

# Implementation: tail -f equivalent
ada logs --tail --format pretty   # Human-readable
ada logs --tail --format json     # Raw JSON lines
```

---

## 6. CLI Commands

### `ada init` (enhanced)

```bash
ada init <path> --name "App Name" --description "Project description..."

# Interactive mode
ada init <path>
> Project name: My App
> Description: A task management application that...
> Created .ada/project.json
> Created feature-list.json
```

### `ada logs`

```bash
# List recent sessions
ada logs [path]
  SESSION              FEATURE        OUTCOME   TURNS  COST    DURATION
  20240115_003         user-auth      success   23     $0.72   15m
  20240115_002         user-auth      handoff   15     $0.58   12m
  20240115_001         initializer    success   8      $0.25   5m

# View specific session
ada logs --session 20240115_002

# Filter options
ada logs --feature user-auth      # By feature
ada logs --outcome failure        # By outcome
ada logs --since 2024-01-14       # By date
ada logs --errors                 # Only sessions with errors

# Real-time
ada logs --tail                   # Follow current session
ada logs --tail --format json     # Raw JSON output

# Export for analysis
ada logs --export logs.jsonl      # Export all to single file
ada logs --export --session 002   # Export specific session
```

### `ada info`

```bash
ada info <path>
  Project: My Application
  Description: A task management app that allows users to...
  Created: 2024-01-15

  Sessions: 45 total
  Features: 12 (8 completed, 3 in progress, 1 pending)
  Total Cost: $28.45
  Total Time: 4h 32m

  Log Size: 52MB / 100MB limit
```

---

## 7. Data Model Changes

### New Models

```python
# models.py additions

class LogEntryType(str, Enum):
    """Types of log entries."""
    SESSION_START = "session_start"
    PROMPT = "prompt"
    ASSISTANT = "assistant"
    TOOL_RESULT = "tool_result"
    CONTEXT_UPDATE = "context_update"
    ERROR = "error"
    SESSION_END = "session_end"


class ProjectContext(BaseModel):
    """Project metadata and initial context."""
    version: str = "1.0"
    name: str
    description: str
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "user"

    context: dict = Field(default_factory=dict)
    init_session: Optional[dict] = None


class SessionLogEntry(BaseModel):
    """A single entry in a session log."""
    type: LogEntryType
    timestamp: datetime = Field(default_factory=datetime.now)
    turn: Optional[int] = None
    # ... type-specific fields


class SessionIndex(BaseModel):
    """Index of all sessions for fast lookup."""
    version: str = "1.0"
    total_sessions: int = 0
    total_size_bytes: int = 0
    sessions: list[SessionIndexEntry] = Field(default_factory=list)


class SessionIndexEntry(BaseModel):
    """Summary entry in session index."""
    session_id: str
    file: str
    agent_type: str
    feature_id: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    outcome: Optional[str]
    turns: int = 0
    tokens_total: int = 0
    cost_usd: float = 0.0
    size_bytes: int = 0
    archived: bool = False
    archive_file: Optional[str] = None
```

---

## 8. Migration Path

### For Existing Projects

```bash
ada migrate <path>

# Actions:
# 1. Create .ada/ directory structure
# 2. Move .ada_session_state.json → .ada/state/session.json
# 3. Move .ada_session_history.json → .ada/state/history.json
# 4. Move .ada_alerts.json → .ada/alerts.json
# 5. Create project.json from feature-list.json name
# 6. Add .ada/ patterns to .gitignore
```

### Gitignore Updates

```gitignore
# ADA workspace (logs contain sensitive data)
.ada/logs/
.ada/state/
.ada/alerts.json

# Keep these in git
# .ada/project.json
# .ada/config.json
# .ada/prompts/
# .ada/hooks/
```

---

## 9. Future Analysis Opportunities

With full session logs, you can later build:

1. **Failure Pattern Analysis**
   - Which tool calls fail most often?
   - What prompts lead to loops or stuck states?
   - Common error categories by feature type

2. **Cost Optimization**
   - Token usage patterns by agent type
   - Context growth rate analysis
   - Optimal handoff thresholds

3. **Quality Metrics**
   - Turns to completion by feature complexity
   - Files changed per session
   - Test coverage correlation

4. **Prompt Engineering**
   - A/B test different prompt versions
   - Identify which instructions agents ignore
   - Extract successful patterns

5. **Training Data**
   - Export successful sessions for fine-tuning
   - Build examples of good tool usage
   - Create regression test suites

---

## 10. Implementation Phases

### Phase 1: Foundation
- [ ] Create `SessionLogger` class with JSONL writing
- [ ] Add `project.json` creation to `ada init`
- [ ] Implement basic log file naming/rotation
- [ ] Update harness to use SessionLogger

### Phase 2: CLI
- [ ] `ada logs` command with list/view/filter
- [ ] `ada logs --tail` real-time streaming
- [ ] `ada info` command
- [ ] `ada migrate` for existing projects

### Phase 3: Integration
- [ ] Wire logging into CLISession
- [ ] Wire logging into SDKSession
- [ ] Update index.json on session end
- [ ] Implement 100MB rotation

### Phase 4: Polish
- [ ] Pretty formatting for `ada logs`
- [ ] Export functionality
- [ ] Dashboard integration (WebSocket streaming)
