You are analyzing project documentation to extract requirements and planned features.

Given the following documentation, identify:

1. **Planned Features**: Features mentioned as planned, upcoming, or TODO
2. **Incomplete Features**: Features documented but only partially implemented
3. **Documented Requirements**: Functionality that documentation says should exist
4. **Technical Debt**: Known issues or improvements mentioned in docs

## For Each Requirement, Determine

- **title**: A concise name (max 80 characters)
- **description**: What the requirement involves
- **status**: One of:
  - `implemented` - Fully completed based on documentation
  - `partial` - Started but not complete (WIP, in progress)
  - `not_implemented` - Planned but not started
  - `unknown` - Cannot determine status from documentation
- **confidence**: Your confidence in the status determination (0.0 to 1.0)

## Output Format

```json
[
  {
    "title": "OAuth2 authentication with social providers",
    "description": "Support login via Google, GitHub, and Microsoft accounts using OAuth2 flow",
    "status": "partial",
    "confidence": 0.7
  },
  {
    "title": "Export data to CSV format",
    "description": "Allow users to export their data in CSV format for backup or analysis",
    "status": "not_implemented",
    "confidence": 0.9
  }
]
```

## Guidelines

- Focus on actionable, specific requirements
- Skip vague statements like "improve performance" unless they include specifics
- Skip documentation about already-working core functionality
- Skip installation instructions and basic usage documentation
- Include TODO items, roadmap entries, and future plans
- For task lists (- [ ] or - [x]), interpret checkmarks as implementation status

## What to Look For

- Task list items: `- [ ] Feature` (not done) or `- [x] Feature` (done)
- Headers like: TODO, PLANNED, ROADMAP, FUTURE, UPCOMING
- Sections titled: "Planned Features", "Coming Soon", "Future Work"
- Comments like: "TODO:", "FIXME:", "WIP:", "PLANNED:"
- Roadmap entries with version numbers or dates

DOCUMENTATION:
