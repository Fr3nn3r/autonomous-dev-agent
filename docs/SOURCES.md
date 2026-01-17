# Sources & References

This document lists all sources used in designing and implementing the Autonomous Development Agent harness.

## Anthropic Official Documentation

### Engineering Blog Posts

| Title | URL | Key Concepts |
|-------|-----|--------------|
| Effective harnesses for long-running agents | https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents | Two-agent pattern, progress file, JSON backlog, handoff mechanisms |
| Building agents with the Claude Agent SDK | https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk | Agent loop, context management, tools, verification patterns |
| Enabling Claude Code to work more autonomously | https://www.anthropic.com/news/enabling-claude-code-to-work-more-autonomously | Subagents, hooks, background tasks, checkpoints |

### SDK Documentation

| Topic | URL |
|-------|-----|
| Agent SDK Overview | https://platform.claude.com/docs/en/agent-sdk/overview |
| Python SDK Reference | https://platform.claude.com/docs/en/agent-sdk/python |
| Session Management | https://platform.claude.com/docs/en/agent-sdk/sessions |
| Cost Tracking | https://platform.claude.com/docs/en/agent-sdk/cost-tracking |
| Hooks | https://platform.claude.com/docs/en/agent-sdk/hooks |
| Usage & Cost API | https://platform.claude.com/docs/en/build-with-claude/usage-cost-api |

## Key Quotes from Research

### On Context Window Limitations

> "Out of the box, even a frontier coding model like Opus 4.5 running on the Claude Agent SDK in a loop across multiple context windows will fall short of building a production-quality web app with only a high-level prompt."
>
> — Effective harnesses for long-running agents

### On the Two-Agent Solution

> "A two-fold solution: an initializer agent that sets up the environment on the first run, and a coding agent that makes incremental progress in every session while leaving clear artifacts for the next session."
>
> — Effective harnesses for long-running agents

### On Progress Tracking

> "The key insight was finding a way for agents to quickly understand the state of work when starting with a fresh context window, accomplished with the claude-progress.txt file alongside git history."
>
> — Effective harnesses for long-running agents

### On JSON vs Markdown Backlogs

> "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality - use JSON format (models less likely to corrupt than Markdown)."
>
> — Effective harnesses for long-running agents

### On Verification

> "Test as human users would, not just unit tests. Verify features work after implementation before marking complete."
>
> — Effective harnesses for long-running agents

### On Context Management

> "Compaction isn't sufficient. This happens even with compaction, which doesn't always pass perfectly clear instructions to the next agent."
>
> — Effective harnesses for long-running agents

## Third-Party Resources

| Title | URL | Notes |
|-------|-----|-------|
| The Complete Guide to Building Agents | https://nader.substack.com/p/the-complete-guide-to-building-agents | Community guide with practical examples |
| A practical guide to the Python Claude Code SDK | https://www.eesel.ai/blog/python-claude-code-sdk | SDK usage patterns |

## Package Dependencies

| Package | Purpose | Documentation |
|---------|---------|---------------|
| claude-agent-sdk | Core SDK for agent invocation | https://pypi.org/project/claude-agent-sdk/ |
| pydantic | Data validation and models | https://docs.pydantic.dev/ |
| click | CLI framework | https://click.palletsprojects.com/ |
| rich | Terminal formatting | https://rich.readthedocs.io/ |

## Research Date

This implementation is based on research conducted in January 2025, reflecting the state of the Claude Agent SDK and best practices at that time.
