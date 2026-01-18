"""Requirements extraction from documentation.

Analyzes documentation to identify planned features and their implementation status.
"""

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ExtractedRequirement:
    """A requirement extracted from documentation."""

    id: str
    title: str
    description: str
    source_file: str
    source_line: int | None
    status: str  # "implemented", "partial", "not_implemented", "unknown"
    confidence: float  # 0.0 to 1.0


# Documentation files to analyze
DOCUMENTATION_FILES: list[str] = [
    "README.md",
    "README.rst",
    "README.txt",
    "README",
    "docs/README.md",
    "doc/README.md",
    "ROADMAP.md",
    "TODO.md",
    "FEATURES.md",
    "SPEC.md",
    "DESIGN.md",
    "docs/DESIGN.md",
    "docs/design.md",
    "docs/spec.md",
    "docs/features.md",
]

# Patterns that indicate planned features in markdown
FEATURE_PATTERNS: list[str] = [
    r"^[-*]\s*\[([ x])\]\s*(.+)$",  # Task list items: - [ ] Feature or - [x] Done
    r"^#+\s*(TODO|PLANNED|UPCOMING|FUTURE):\s*(.+)$",  # Headers with TODO prefix
    r"^[-*]\s*(TODO|PLANNED|WIP):\s*(.+)$",  # List items with TODO prefix
]

# Patterns indicating implementation status
IMPLEMENTED_INDICATORS: list[str] = [
    "[x]",
    "DONE",
    "COMPLETED",
    "IMPLEMENTED",
    "RELEASED",
]

NOT_IMPLEMENTED_INDICATORS: list[str] = [
    "[ ]",
    "TODO",
    "PLANNED",
    "FUTURE",
    "WIP",
    "IN PROGRESS",
    "NOT IMPLEMENTED",
]


def get_requirements_prompt() -> str:
    """Get the requirements extraction prompt template.

    Returns:
        Prompt template string.
    """
    # Try to load custom prompt
    prompt_paths = [
        Path(__file__).parent.parent / "prompts" / "discovery_requirements.txt",
        Path(__file__).parent.parent.parent.parent / ".ada" / "prompts" / "discovery_requirements.txt",
    ]

    for prompt_path in prompt_paths:
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")

    # Default prompt
    return """You are analyzing project documentation to extract requirements and planned features.

Given the following documentation, identify:
1. Planned features that are mentioned but may not be implemented
2. Documented functionality that should exist
3. TODO items and roadmap items

For each requirement, determine:
- A short title (max 80 chars)
- A description of the requirement
- Implementation status: "implemented", "partial", "not_implemented", or "unknown"
- Confidence (0.0 to 1.0) in your status determination

Output as a JSON array:
```json
[
  {
    "title": "User authentication",
    "description": "OAuth2-based user authentication with Google and GitHub providers",
    "status": "partial",
    "confidence": 0.7
  }
]
```

Only include clear, actionable requirements. Skip vague statements or already-implemented core functionality.

DOCUMENTATION:
"""


class RequirementsExtractor:
    """Extracts requirements from project documentation."""

    def __init__(
        self,
        project_path: Path | str,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize the extractor.

        Args:
            project_path: Path to the project root directory.
            model: Claude model for AI-powered extraction.
        """
        self.project_path = Path(project_path).resolve()
        self.model = model
        self._prompt_template = get_requirements_prompt()

    def extract(self, use_ai: bool = False) -> list[ExtractedRequirement]:
        """Extract requirements from documentation.

        Args:
            use_ai: Whether to use Claude for deeper analysis.

        Returns:
            List of extracted requirements.
        """
        requirements = []

        # First, do static extraction from markdown
        requirements.extend(self._extract_from_markdown())

        # Optionally use AI for deeper analysis
        if use_ai:
            requirements.extend(self._extract_with_ai())

        # Deduplicate by title
        seen_titles: set[str] = set()
        unique_requirements = []
        for req in requirements:
            title_lower = req.title.lower()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_requirements.append(req)

        return unique_requirements

    def _extract_from_markdown(self) -> list[ExtractedRequirement]:
        """Extract requirements using static markdown parsing.

        Returns:
            List of extracted requirements.
        """
        requirements = []

        for doc_file in DOCUMENTATION_FILES:
            doc_path = self.project_path / doc_file
            if not doc_path.exists():
                continue

            try:
                content = doc_path.read_text(encoding="utf-8", errors="ignore")
                requirements.extend(self._parse_markdown_file(content, doc_file))
            except (OSError, IOError):
                continue

        return requirements

    def _parse_markdown_file(
        self,
        content: str,
        source_file: str,
    ) -> list[ExtractedRequirement]:
        """Parse a markdown file for requirements.

        Args:
            content: File content.
            source_file: Source file path.

        Returns:
            List of extracted requirements.
        """
        requirements = []
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            # Check for task list items
            task_match = re.match(r'^[-*]\s*\[([ xX])\]\s*(.+)$', line)
            if task_match:
                is_done = task_match.group(1).lower() == 'x'
                text = task_match.group(2).strip()

                requirements.append(ExtractedRequirement(
                    id=self._generate_id(source_file, text),
                    title=text[:80],
                    description=text,
                    source_file=source_file,
                    source_line=line_num,
                    status="implemented" if is_done else "not_implemented",
                    confidence=0.9,  # High confidence for explicit task lists
                ))
                continue

            # Check for TODO/PLANNED prefixes
            todo_match = re.match(r'^[-*]?\s*(TODO|PLANNED|WIP|FIXME):\s*(.+)$', line, re.IGNORECASE)
            if todo_match:
                prefix = todo_match.group(1).upper()
                text = todo_match.group(2).strip()

                status = "partial" if prefix == "WIP" else "not_implemented"

                requirements.append(ExtractedRequirement(
                    id=self._generate_id(source_file, text),
                    title=text[:80],
                    description=text,
                    source_file=source_file,
                    source_line=line_num,
                    status=status,
                    confidence=0.85,
                ))
                continue

        return requirements

    def _extract_with_ai(self) -> list[ExtractedRequirement]:
        """Extract requirements using Claude AI.

        Returns:
            List of extracted requirements.
        """
        # Gather documentation content
        docs_content = []

        for doc_file in DOCUMENTATION_FILES:
            doc_path = self.project_path / doc_file
            if not doc_path.exists():
                continue

            try:
                content = doc_path.read_text(encoding="utf-8", errors="ignore")
                # Limit size
                if len(content) > 20000:
                    content = content[:20000] + "\n... (truncated)"
                docs_content.append(f"=== {doc_file} ===\n{content}")
            except (OSError, IOError):
                continue

        if not docs_content:
            return []

        # Build prompt
        prompt = self._prompt_template + "\n\n" + "\n\n".join(docs_content)

        # Call Claude
        response = self._call_claude(prompt)

        # Parse response
        return self._parse_ai_response(response)

    def _call_claude(self, prompt: str) -> str:
        """Call Claude CLI with the prompt.

        Args:
            prompt: The prompt to send.

        Returns:
            Claude's response text.
        """
        try:
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
                timeout=120,
                cwd=self.project_path,
            )

            if result.returncode == 0:
                return result.stdout
            return ""

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return ""

    def _parse_ai_response(self, response: str) -> list[ExtractedRequirement]:
        """Parse Claude's response into requirements.

        Args:
            response: Claude's response text.

        Returns:
            List of parsed requirements.
        """
        if not response:
            return []

        # Extract JSON from response
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                json_str = json_match.group(0)
            else:
                return []

        try:
            items = json.loads(json_str)
            if not isinstance(items, list):
                return []

            requirements = []
            for item in items:
                req = self._parse_ai_item(item)
                if req:
                    requirements.append(req)

            return requirements

        except json.JSONDecodeError:
            return []

    def _parse_ai_item(self, item: dict[str, Any]) -> ExtractedRequirement | None:
        """Parse a single requirement item from AI response.

        Args:
            item: Dictionary with requirement data.

        Returns:
            ExtractedRequirement or None if invalid.
        """
        try:
            title = item.get("title", "")
            if not title:
                return None

            status = item.get("status", "unknown")
            if status not in {"implemented", "partial", "not_implemented", "unknown"}:
                status = "unknown"

            confidence = float(item.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            return ExtractedRequirement(
                id=self._generate_id("ai_extracted", title),
                title=title[:80],
                description=item.get("description", title),
                source_file="AI analysis",
                source_line=None,
                status=status,
                confidence=confidence,
            )

        except (KeyError, ValueError, TypeError):
            return None

    def _generate_id(self, source: str, title: str) -> str:
        """Generate a unique ID for a requirement.

        Args:
            source: Source identifier.
            title: Requirement title.

        Returns:
            Unique ID string.
        """
        hash_input = f"{self.project_path}:{source}:{title}"
        return f"req-{hashlib.md5(hash_input.encode()).hexdigest()[:12]}"
