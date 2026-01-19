You are an expert software architect analyzing an application specification to create a structured feature backlog for an autonomous development agent.

## Your Task

Analyze the application specification below and generate a comprehensive, implementation-ready feature backlog in JSON format. The backlog should break down the application into discrete, testable features that can be implemented incrementally by an AI coding agent.

## Key Principles

1. **Foundational First**: Order features so infrastructure and foundational features come before features that depend on them
2. **Meaningful Deliverables**: Each feature should be a complete, demoable unit of functionality—not just a code change
3. **Clear Boundaries**: Features should have clear start and end points with explicit acceptance criteria
4. **Test-Driven**: Include verification steps that can be tested programmatically where possible
5. **Dependency Aware**: Explicitly declare dependencies between features

## Feature Scoping Guidelines

**The Right Size**: A well-scoped feature is one that:
- Can be completed in a single coding session (typically 30-60 minutes of agent work)
- Produces a visible or testable outcome when complete
- Makes sense to demo or describe independently ("We added X")
- Has 3-6 acceptance criteria

**Avoid Fragmentation**: Do NOT create separate features for:
- A UI component and its corresponding API endpoint (combine them)
- Multiple similar controls (e.g., 5 slider parameters → 1 "Parameter Controls" feature)
- Toggle + integration (a toggle without its integration is useless)
- Import + export (these are typically implemented together)
- Tightly coupled setup steps (e.g., CSS variables + Tailwind config + theme provider → 1 "Theme System" feature)

**When to Split**: Only split features when:
- They can genuinely be delivered and tested independently
- They have different priorities or could be deferred separately
- They touch completely different parts of the codebase

## Requirements

- Generate an appropriate number of features for the project scope (typically 40-80 for a full application)
- The {min_features}-{max_features} range is a guideline, not a target—prioritize proper scoping over hitting a number
- Ensure every feature has clear acceptance criteria
- Use priority scores: 100 (critical/foundational) down to 0 (optional enhancements)
- Categories help organize work: infrastructure first, then functional features, then testing/docs

## Output Format

Return a JSON array of features. Each feature MUST include:

| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique kebab-case identifier (e.g., "user-authentication") |
| name | string | Short descriptive name (max 60 chars) |
| description | string | Detailed description of what to implement |
| category | string | One of: "functional", "infrastructure", "testing", "documentation", "bugfix", "refactor" |
| priority | integer | 100 (highest) to 0 (lowest) |
| acceptance_criteria | array[string] | Conditions that must be met for the feature to be complete |
| steps | array[string] | Optional: Step-by-step implementation or test verification steps |
| depends_on | array[string] | Optional: IDs of features this depends on |

## Priority Guidelines

- **100**: Project setup, core configuration, critical infrastructure
- **90-80**: Core data models, database setup, essential services
- **70-60**: Primary user-facing features, main functionality
- **50-40**: Secondary features, enhancements
- **30-20**: Testing, documentation, nice-to-haves
- **10-0**: Optional polish, future considerations

## Category Guidelines

- **infrastructure**: Project setup, config, build tools, deployment, CI/CD
- **functional**: User-facing features, business logic, APIs
- **testing**: Test suites, test utilities, coverage
- **documentation**: README, API docs, user guides
- **bugfix**: Bug fixes (rarely used for new projects)
- **refactor**: Code improvements (rarely used for new projects)

## Example Output

```json
[
  {{
    "id": "project-setup",
    "name": "Project Initialization",
    "description": "Set up the project structure with package manager, dependencies, and essential configuration files. This establishes the foundation for all subsequent development.",
    "category": "infrastructure",
    "priority": 100,
    "acceptance_criteria": [
      "Package.json created with project metadata",
      "Core dependencies installed successfully",
      "TypeScript/ESLint/Prettier configured",
      "Git repository initialized with .gitignore"
    ],
    "steps": [
      "Run npm init to create package.json",
      "Install core dependencies",
      "Configure TypeScript with tsconfig.json",
      "Set up linting and formatting",
      "Create initial directory structure"
    ],
    "depends_on": []
  }},
  {{
    "id": "theme-system",
    "name": "Theme System with Dark/Light Mode",
    "description": "Implement complete theming infrastructure including CSS variables, Tailwind configuration, theme provider, and toggle UI. Supports light/dark modes with smooth transitions.",
    "category": "infrastructure",
    "priority": 90,
    "acceptance_criteria": [
      "CSS variables defined for all color tokens",
      "Tailwind configured to use CSS variables",
      "Theme provider wraps application with context",
      "Theme toggle UI allows switching modes",
      "Theme preference persists in localStorage",
      "Smooth transition animation on theme change"
    ],
    "steps": [
      "Define CSS custom properties for light and dark themes",
      "Configure Tailwind to reference CSS variables",
      "Create ThemeProvider component with React context",
      "Build theme toggle component",
      "Add localStorage persistence"
    ],
    "depends_on": ["project-setup"]
  }},
  {{
    "id": "document-upload",
    "name": "Document Upload and Context Integration",
    "description": "Allow users to upload documents (PDF, TXT, MD) that are processed and made available as context for AI conversations. Includes upload UI, backend processing, and chat integration.",
    "category": "functional",
    "priority": 70,
    "acceptance_criteria": [
      "Drag-and-drop upload UI with file type validation",
      "Backend endpoint processes uploads and extracts text",
      "Uploaded documents shown as badges in chat",
      "Document content included in AI context",
      "Users can remove documents from context"
    ],
    "depends_on": ["chat-interface", "api-foundation"]
  }}
]
```

## Anti-Pattern Examples (Do NOT generate like this)

**Too Fragmented** - These should be ONE feature:
- ❌ "Temperature Slider Control" + "Max Tokens Input" + "Top-P Slider" + "Frequency Penalty Slider"
- ✅ "Model Parameter Controls" (all sliders in one feature)

**Incomplete Without Pair** - These must be combined:
- ❌ "Document Upload UI" (no backend) + "Document Upload Endpoint" (no UI) + "Document Context Integration"
- ✅ "Document Upload and Context Integration" (complete end-to-end feature)

**Arbitrary Split** - Configuration that belongs together:
- ❌ "CSS Theme Variables" + "Tailwind Theme Config" + "Theme Provider Setup"
- ✅ "Theme System" (all configuration in one coherent feature)

---

## Application Specification to Analyze

{spec_content}

---

Now generate the complete feature backlog as a JSON array. Output ONLY the JSON array with no additional text, explanation, or markdown formatting outside the JSON.
