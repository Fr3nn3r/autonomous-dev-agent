You are an expert software architect analyzing an application specification to create a structured feature backlog for an autonomous development agent.

## Your Task

Analyze the application specification below and generate a comprehensive, implementation-ready feature backlog in JSON format. The backlog should break down the application into discrete, testable features that can be implemented incrementally by an AI coding agent.

## Key Principles

1. **Foundational First**: Order features so infrastructure and foundational features come before features that depend on them
2. **Discrete Units**: Each feature should be a single, testable unit of work (typically completable in one coding session)
3. **Clear Boundaries**: Features should have clear start and end points with explicit acceptance criteria
4. **Test-Driven**: Include verification steps that can be tested programmatically where possible
5. **Dependency Aware**: Explicitly declare dependencies between features

## Requirements

- Generate between {min_features} and {max_features} features
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
    "id": "database-schema",
    "name": "Database Schema Design",
    "description": "Design and implement the database schema with all required tables, relationships, and indexes. Use migrations for version control.",
    "category": "infrastructure",
    "priority": 95,
    "acceptance_criteria": [
      "All tables defined with appropriate columns",
      "Foreign key relationships established",
      "Indexes created for frequently queried columns",
      "Migrations run successfully"
    ],
    "steps": [
      "Create migration files for each table",
      "Define relationships between entities",
      "Add appropriate indexes",
      "Run migrations and verify schema"
    ],
    "depends_on": ["project-setup"]
  }},
  {{
    "id": "user-authentication",
    "name": "User Authentication System",
    "description": "Implement user registration, login, and session management with secure password hashing and JWT tokens.",
    "category": "functional",
    "priority": 85,
    "acceptance_criteria": [
      "Users can register with email and password",
      "Users can log in and receive JWT token",
      "Passwords are securely hashed",
      "Protected routes require valid token"
    ],
    "steps": [
      "Create user model with password hashing",
      "Implement registration endpoint",
      "Implement login endpoint with JWT generation",
      "Create authentication middleware",
      "Add tests for auth flows"
    ],
    "depends_on": ["database-schema"]
  }}
]
```

---

## Application Specification to Analyze

{spec_content}

---

Now generate the complete feature backlog as a JSON array. Output ONLY the JSON array with no additional text, explanation, or markdown formatting outside the JSON.
