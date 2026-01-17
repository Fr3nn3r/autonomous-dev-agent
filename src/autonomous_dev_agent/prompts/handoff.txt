You are completing a development session and need to create a proper handoff.

## Session Summary
- Session ID: {session_id}
- Feature: {feature_name} ({feature_id})
- Context Usage: {context_usage}%

## Handoff Requirements

You must now prepare for the next session to take over. Complete these steps:

### 1. Finalize Current Work
- Ensure all files are saved
- Run the test suite one final time
- Fix any failing tests if possible

### 2. Stage and Commit
```bash
git add -A
git status  # Review what will be committed
git commit -m "{commit_message}"
```

### 3. Update Progress File
Add a HANDOFF section to claude-progress.txt with:

```
==============================================================
[HANDOFF] Session {session_id} - {timestamp}

## What Was Accomplished
- [List specific accomplishments]

## Current State
- Feature {feature_id} status: [in_progress/completed]
- All tests: [passing/X failing]
- Code state: [clean/needs attention]

## Files Changed
- [List key files modified]

## Next Steps for Incoming Session
1. [Specific next action]
2. [Following action]
3. [etc.]

## Notes/Warnings
- [Any important context the next session needs]
==============================================================
```

### 4. Final Verification
- Confirm commit was successful: `git log -1`
- Verify progress file was updated
- Ensure no uncommitted changes remain

## Context for Next Session
The next session will:
1. Read the progress file to understand current state
2. Read git history for additional context
3. Continue from where you left off

Make your handoff notes clear enough that someone unfamiliar with the session could pick up immediately.
