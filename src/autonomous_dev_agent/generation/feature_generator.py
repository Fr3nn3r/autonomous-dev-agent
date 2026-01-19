"""AI-driven feature generation from application specifications.

Uses Claude to analyze a specification file and generate a structured
feature backlog in JSON format.
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..models import (
    Backlog,
    Feature,
    FeatureCategory,
    FeatureStatus,
)
from .spec_parser import ParsedSpec, SpecParser


# Default model for feature generation
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Default feature count limits
DEFAULT_MIN_FEATURES = 20
DEFAULT_MAX_FEATURES = 50

# Category mapping from string to enum
CATEGORY_MAP: dict[str, FeatureCategory] = {
    "functional": FeatureCategory.FUNCTIONAL,
    "bugfix": FeatureCategory.BUGFIX,
    "refactor": FeatureCategory.REFACTOR,
    "testing": FeatureCategory.TESTING,
    "documentation": FeatureCategory.DOCUMENTATION,
    "infrastructure": FeatureCategory.INFRASTRUCTURE,
}


@dataclass
class GeneratedBacklog:
    """Result of generating a backlog from a specification."""

    backlog: Backlog
    spec_path: Path
    model_used: str
    generation_time: datetime = field(default_factory=datetime.now)
    raw_response: str = ""

    @property
    def feature_count(self) -> int:
        """Get the number of generated features."""
        return len(self.backlog.features)


def get_prompt_template() -> str:
    """Load the backlog generation prompt template.

    Returns:
        Prompt template string.
    """
    # Check for custom prompt in prompts directory
    prompt_paths = [
        Path(__file__).parent.parent / "prompts" / "generate_backlog.txt",
    ]

    for prompt_path in prompt_paths:
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")

    # Default prompt if file not found
    return _get_default_prompt()


def _get_default_prompt() -> str:
    """Get the default prompt template."""
    return '''You are an expert software architect analyzing an application specification to create a structured feature backlog.

## Task
Analyze the specification below and generate a comprehensive feature backlog in JSON format. Break down the application into implementable features, ordered by implementation priority (foundational features first).

## Requirements
- Generate between {min_features} and {max_features} features
- Each feature should be a discrete, testable unit of work
- Order features so foundational/infrastructure features come first
- Include clear acceptance criteria for each feature
- Consider dependencies between features

## Output Format
Return a JSON array of features. Each feature must have:
- id: kebab-case unique identifier (e.g., "user-authentication")
- name: Short descriptive name
- description: Detailed description of what to implement
- category: One of "functional", "infrastructure", "testing", "documentation", "bugfix", "refactor"
- priority: Integer from 100 (highest) to 0 (lowest)
- acceptance_criteria: Array of verification conditions
- steps: Array of implementation/testing steps (optional)
- depends_on: Array of feature IDs this depends on (optional)

## Example Output
```json
[
  {{
    "id": "project-setup",
    "name": "Project Setup and Configuration",
    "description": "Initialize the project with required dependencies and configuration files.",
    "category": "infrastructure",
    "priority": 100,
    "acceptance_criteria": [
      "Package manager initialized",
      "Core dependencies installed",
      "Configuration files created"
    ],
    "steps": [
      "Initialize package.json with project metadata",
      "Install core dependencies",
      "Create configuration files"
    ],
    "depends_on": []
  }}
]
```

## Specification to Analyze

{spec_content}

---

Generate the feature backlog as a JSON array. Output ONLY the JSON array, no additional text.'''


class FeatureGenerator:
    """Generates feature backlogs from specifications using Claude AI."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        min_features: int = DEFAULT_MIN_FEATURES,
        max_features: int = DEFAULT_MAX_FEATURES,
    ):
        """Initialize the generator.

        Args:
            model: Claude model to use for generation.
            min_features: Minimum number of features to generate.
            max_features: Maximum number of features to generate.
        """
        self.model = model
        self.min_features = min_features
        self.max_features = max_features
        self._prompt_template = get_prompt_template()

    def generate(
        self,
        spec: ParsedSpec,
        project_name: str | None = None,
        project_path: Path | str | None = None,
    ) -> GeneratedBacklog:
        """Generate a feature backlog from a specification.

        Args:
            spec: Parsed specification to generate from.
            project_name: Name for the project (default: spec title or filename).
            project_path: Path for the project (default: spec parent directory).

        Returns:
            GeneratedBacklog with the generated features.

        Raises:
            RuntimeError: If Claude CLI fails or returns invalid JSON.
        """
        # Determine project metadata
        if project_name is None:
            project_name = spec.title or spec.file_path.stem

        if project_path is None:
            project_path = spec.file_path.parent
        project_path = Path(project_path).resolve()

        # Build the prompt
        prompt = self._prompt_template.format(
            min_features=self.min_features,
            max_features=self.max_features,
            spec_content=spec.get_truncated_content(),
        )

        # Call Claude CLI
        response = self._call_claude(prompt)

        if not response:
            raise RuntimeError("Claude CLI returned empty response")

        # Parse the response
        features = self._parse_response(response)

        if not features:
            raise RuntimeError(
                "Failed to parse features from Claude response. "
                "Check that Claude returned valid JSON."
            )

        # Build the backlog
        backlog = Backlog(
            project_name=project_name,
            project_path=str(project_path),
            features=features,
        )

        return GeneratedBacklog(
            backlog=backlog,
            spec_path=spec.file_path,
            model_used=self.model,
            raw_response=response,
        )

    def generate_from_file(
        self,
        spec_path: Path | str,
        project_name: str | None = None,
        project_path: Path | str | None = None,
    ) -> GeneratedBacklog:
        """Generate a backlog directly from a specification file.

        Args:
            spec_path: Path to the specification file.
            project_name: Name for the project.
            project_path: Path for the project.

        Returns:
            GeneratedBacklog with the generated features.
        """
        parser = SpecParser(spec_path)
        spec = parser.parse()
        return self.generate(spec, project_name, project_path)

    def _call_claude(self, prompt: str) -> str:
        """Call Claude CLI with the prompt.

        Args:
            prompt: The prompt to send.

        Returns:
            Claude's response text.

        Raises:
            RuntimeError: If Claude CLI is not available or times out.
        """
        try:
            # Use Claude CLI in print mode (non-interactive)
            result = subprocess.run(
                [
                    "claude",
                    "--print",
                    "--model", self.model,
                    "--max-turns", "1",
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=180,  # 3 minute timeout for generation
            )

            if result.returncode == 0:
                return result.stdout
            else:
                error_msg = result.stderr or "Unknown error"
                raise RuntimeError(f"Claude CLI failed: {error_msg}")

        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI timed out after 3 minutes")
        except FileNotFoundError:
            raise RuntimeError(
                "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            )

    def _parse_response(self, response: str) -> list[Feature]:
        """Parse Claude's response into Feature objects.

        Args:
            response: Claude's response text.

        Returns:
            List of parsed Feature objects.
        """
        # Extract JSON from response (may be wrapped in markdown code blocks)
        json_str = self._extract_json(response)

        if not json_str:
            return []

        try:
            features_data = json.loads(json_str)

            if not isinstance(features_data, list):
                return []

            features = []
            for item in features_data:
                feature = self._parse_feature_item(item)
                if feature:
                    features.append(feature)

            return features

        except json.JSONDecodeError:
            return []

    def _extract_json(self, response: str) -> str | None:
        """Extract JSON array from response text.

        Handles JSON wrapped in markdown code blocks or raw JSON.

        Args:
            response: Response text.

        Returns:
            JSON string or None.
        """
        # Try to find JSON in markdown code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
        if json_match:
            return json_match.group(1).strip()

        # Try to find raw JSON array
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            return json_match.group(0)

        return None

    def _parse_feature_item(self, item: dict) -> Feature | None:
        """Parse a single feature item from JSON.

        Args:
            item: Dictionary with feature data.

        Returns:
            Feature or None if invalid.
        """
        try:
            # Required fields
            feature_id = item.get("id", "")
            name = item.get("name", "")
            description = item.get("description", "")

            if not feature_id or not name:
                return None

            # Parse category
            category_str = item.get("category", "functional").lower()
            category = CATEGORY_MAP.get(category_str, FeatureCategory.FUNCTIONAL)

            # Parse priority
            priority = item.get("priority", 50)
            if not isinstance(priority, int):
                try:
                    priority = int(priority)
                except (ValueError, TypeError):
                    priority = 50
            priority = max(0, min(100, priority))  # Clamp to 0-100

            # Parse optional lists
            acceptance_criteria = item.get("acceptance_criteria", [])
            if not isinstance(acceptance_criteria, list):
                acceptance_criteria = []
            acceptance_criteria = [str(c) for c in acceptance_criteria if c]

            steps = item.get("steps", [])
            if not isinstance(steps, list):
                steps = []
            steps = [str(s) for s in steps if s]

            depends_on = item.get("depends_on", [])
            if not isinstance(depends_on, list):
                depends_on = []
            depends_on = [str(d) for d in depends_on if d]

            return Feature(
                id=feature_id,
                name=name,
                description=description,
                category=category,
                status=FeatureStatus.PENDING,
                priority=priority,
                acceptance_criteria=acceptance_criteria,
                steps=steps,
                depends_on=depends_on,
                source="generated",
            )

        except (KeyError, ValueError, TypeError):
            return None

    def merge_with_existing(
        self,
        generated: GeneratedBacklog,
        existing: Backlog,
        prefer_generated: bool = False,
    ) -> Backlog:
        """Merge generated backlog with an existing one.

        Args:
            generated: The newly generated backlog.
            existing: Existing backlog to merge with.
            prefer_generated: Whether to prefer generated features on ID conflict.

        Returns:
            Merged backlog.
        """
        merged = Backlog(
            project_name=existing.project_name,
            project_path=existing.project_path,
            features=list(existing.features),
            created_at=existing.created_at,
        )

        existing_ids = {f.id for f in merged.features}

        for feature in generated.backlog.features:
            if feature.id not in existing_ids:
                merged.features.append(feature)
                existing_ids.add(feature.id)
            elif prefer_generated:
                # Replace existing feature
                merged.features = [
                    feature if f.id == feature.id else f
                    for f in merged.features
                ]

        # Sort by priority (descending)
        merged.features.sort(key=lambda f: f.priority, reverse=True)
        merged.last_updated = datetime.now()

        return merged
