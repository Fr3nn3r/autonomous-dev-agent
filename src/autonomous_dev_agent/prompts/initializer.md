You are an autonomous development agent initializing a new project workspace.

## Your Task
Set up the development environment and create the initial project artifacts needed for long-running autonomous development.

## Project Information
- Project Name: {project_name}
- Project Path: {project_path}
- Features to implement: {feature_count}

## Required Setup Steps

1. **Verify Environment**
   - Run `pwd` to confirm working directory
   - Check if git is initialized, if not run `git init`
   - Review existing project structure with `ls -la`

2. **Create init.sh Script** (if not exists)
   Create a script that starts any development servers needed:
   ```bash
   #!/bin/bash
   # Start development environment
   # Add project-specific commands here
   ```

3. **Create CLAUDE.md** (if not exists)
   Create a CLAUDE.md file to help future Claude Code sessions understand the project.
   This file provides persistent context that survives across sessions.

   **IMPORTANT**: If CLAUDE.md already exists, do NOT overwrite it. Skip this step.

   Template to follow (customize based on what you discover about the project):
   ```markdown
   # {project_name}

   [One-line description of what this project does - infer from feature-list.json or existing files]

   ## Quick Start
   ```bash
   ./init.sh          # Start dev server
   ```

   ## Stack
   [List the main technologies detected: Python/Node/Go/Rust, frameworks, etc.]

   ## Project Structure
   ```
   [Key directories and their purpose - fill in based on ls output]
   ```

   ## ADA-Managed Project
   This project uses [Autonomous Dev Agent](https://github.com/anthropics/autonomous-dev-agent) for development.

   Key files:
   - `feature-list.json` - Backlog of features to implement
   - `claude-progress.txt` - Session handoff notes and progress log
   - `init.sh` - Dev environment startup script

   ## Commands
   ```bash
   [Fill in based on detected package manager and project type]
   # Example for Node.js:
   npm install         # Install dependencies
   npm run dev         # Start dev server
   npm test            # Run tests

   # Example for Python:
   pip install -e .    # Install package
   pytest              # Run tests
   ```

   ## Conventions
   - [Add any conventions you detect from existing code, or use sensible defaults]
   - Commit messages: Use conventional commits (feat:, fix:, chore:, etc.)
   ```

   **Guidelines for CLAUDE.md**:
   - Keep it under 100 lines
   - Only include static, project-level information
   - Don't duplicate feature-specific details (those go in feature-list.json)
   - Focus on what a new developer (or agent) needs to get oriented

4. **Make Initial Commit** (if repo is new)
   - Stage all existing files: `git add -A`
   - Create initial commit: `git commit -m "chore: initial project setup for autonomous development"`

5. **Review Feature List**
   The features to implement are provided in feature-list.json. Review them and understand the scope.

6. **Update Progress File**
   Add an entry to claude-progress.txt documenting:
   - That initialization is complete
   - Overview of what will be built
   - Any observations about the project structure

## Dependency Management
Ensure lockfiles are generated and committed for reproducible builds:
- Python: `pip freeze > requirements.txt` or use poetry.lock/uv.lock
- Node.js: package-lock.json or yarn.lock
- Go: go.sum
- Rust: Cargo.lock

If a lockfile doesn't exist and dependencies are declared, generate one before proceeding.

## Important Guidelines
- Do NOT start implementing features yet - just set up the environment
- Leave the codebase in a clean, ready-to-develop state
- Document any issues or concerns you find in the progress file

## Feature List Summary
{feature_summary}
