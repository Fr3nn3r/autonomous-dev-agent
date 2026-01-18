"""AI-powered code review using Claude.

Performs deep code review to find bugs, security issues, and code smells.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from ..models import CodeIssue, IssueCategory, Severity


# Maximum file size to review (in characters)
MAX_FILE_SIZE = 50000

# Maximum files to review per batch
MAX_FILES_PER_BATCH = 5

# File extensions to review
REVIEWABLE_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".rs", ".go", ".java", ".cs",
    ".rb", ".php", ".swift", ".kt",
}

# Directories to skip
SKIP_DIRECTORIES: set[str] = {
    "node_modules", "__pycache__", ".git", "venv", ".venv",
    "dist", "build", "target", ".tox", ".pytest_cache",
    "vendor", "third_party",
}


def get_review_prompt() -> str:
    """Get the code review prompt template.

    Returns:
        Prompt template string.
    """
    # Try to load custom prompt from prompts directory
    prompt_paths = [
        Path(__file__).parent.parent / "prompts" / "discovery_review.txt",
        Path(__file__).parent.parent.parent.parent / ".ada" / "prompts" / "discovery_review.txt",
    ]

    for prompt_path in prompt_paths:
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")

    # Default prompt
    return """You are a code reviewer analyzing code for bugs, security issues, and code quality problems.

Analyze the following code and identify any issues. For each issue found, provide:
1. The file path
2. The line number (if applicable)
3. The severity (critical, high, medium, low)
4. The category (bug, security, performance, code_smell, error_handling, validation, hardcoded, deprecated)
5. A short title (max 80 chars)
6. A description of the issue
7. A suggested fix (optional)

Focus on:
- Bugs and logic errors
- Security vulnerabilities (OWASP Top 10)
- Error handling gaps (unhandled exceptions, missing error checks)
- Hardcoded secrets or credentials
- Performance issues
- Code smells (dead code, code duplication, complex logic)
- Deprecated API usage

Output your findings as a JSON array. If no issues are found, output an empty array.

Format:
```json
[
  {
    "file": "path/to/file.py",
    "line": 42,
    "severity": "high",
    "category": "security",
    "title": "SQL injection vulnerability",
    "description": "User input is directly concatenated into SQL query without sanitization.",
    "suggested_fix": "Use parameterized queries instead of string concatenation."
  }
]
```

CODE TO REVIEW:
"""


class CodeReviewer:
    """AI-powered code reviewer using Claude."""

    def __init__(
        self,
        project_path: Path | str,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize the reviewer.

        Args:
            project_path: Path to the project root directory.
            model: Claude model to use for review.
        """
        self.project_path = Path(project_path).resolve()
        self.model = model
        self._prompt_template = get_review_prompt()

    async def review(
        self,
        files: list[Path] | None = None,
        max_files: int = 20,
    ) -> list[CodeIssue]:
        """Review code files and return issues found.

        Args:
            files: Specific files to review (None = auto-detect).
            max_files: Maximum number of files to review.

        Returns:
            List of CodeIssue objects.
        """
        if files is None:
            files = self._get_reviewable_files(max_files)

        issues = []

        # Process files in batches to stay within context limits
        for i in range(0, len(files), MAX_FILES_PER_BATCH):
            batch = files[i:i + MAX_FILES_PER_BATCH]
            batch_issues = await self._review_batch(batch)
            issues.extend(batch_issues)

        return issues

    def review_sync(
        self,
        files: list[Path] | None = None,
        max_files: int = 20,
    ) -> list[CodeIssue]:
        """Synchronous version of review.

        Args:
            files: Specific files to review (None = auto-detect).
            max_files: Maximum number of files to review.

        Returns:
            List of CodeIssue objects.
        """
        if files is None:
            files = self._get_reviewable_files(max_files)

        issues = []

        # Process files in batches
        for i in range(0, len(files), MAX_FILES_PER_BATCH):
            batch = files[i:i + MAX_FILES_PER_BATCH]
            batch_issues = self._review_batch_sync(batch)
            issues.extend(batch_issues)

        return issues

    async def _review_batch(self, files: list[Path]) -> list[CodeIssue]:
        """Review a batch of files asynchronously.

        Args:
            files: Files to review.

        Returns:
            List of issues found.
        """
        # For now, use sync implementation
        # TODO: Add async Claude API support when available
        return self._review_batch_sync(files)

    def _review_batch_sync(self, files: list[Path]) -> list[CodeIssue]:
        """Review a batch of files synchronously.

        Args:
            files: Files to review.

        Returns:
            List of issues found.
        """
        # Build the prompt with file contents
        prompt = self._prompt_template + "\n\n"

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")

                # Truncate very large files
                if len(content) > MAX_FILE_SIZE:
                    content = content[:MAX_FILE_SIZE] + "\n... (truncated)"

                relative_path = file_path.relative_to(self.project_path)
                prompt += f"=== {relative_path} ===\n{content}\n\n"

            except (OSError, IOError):
                continue

        # Call Claude CLI
        response = self._call_claude(prompt)

        # Parse the response
        return self._parse_response(response)

    def _call_claude(self, prompt: str) -> str:
        """Call Claude CLI with the prompt.

        Args:
            prompt: The prompt to send.

        Returns:
            Claude's response text.
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
                timeout=120,  # 2 minute timeout
                cwd=self.project_path,
            )

            if result.returncode == 0:
                return result.stdout
            else:
                # Log error but don't crash
                return ""

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            # Claude CLI not available or timed out
            return ""

    def _parse_response(self, response: str) -> list[CodeIssue]:
        """Parse Claude's response into CodeIssue objects.

        Args:
            response: Claude's response text.

        Returns:
            List of parsed CodeIssue objects.
        """
        if not response:
            return []

        # Extract JSON from response (it may be wrapped in markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try to find raw JSON array
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                json_str = json_match.group(0)
            else:
                return []

        try:
            issues_data = json.loads(json_str)
            if not isinstance(issues_data, list):
                return []

            issues = []
            for item in issues_data:
                issue = self._parse_issue_item(item)
                if issue:
                    issues.append(issue)

            return issues

        except json.JSONDecodeError:
            return []

    def _parse_issue_item(self, item: dict[str, Any]) -> CodeIssue | None:
        """Parse a single issue item from JSON.

        Args:
            item: Dictionary with issue data.

        Returns:
            CodeIssue or None if invalid.
        """
        try:
            # Required fields
            file_path = item.get("file", "")
            title = item.get("title", "")

            if not file_path or not title:
                return None

            # Parse severity
            severity_str = item.get("severity", "medium").lower()
            severity_map = {
                "critical": Severity.CRITICAL,
                "high": Severity.HIGH,
                "medium": Severity.MEDIUM,
                "low": Severity.LOW,
            }
            severity = severity_map.get(severity_str, Severity.MEDIUM)

            # Parse category
            category_str = item.get("category", "code_smell").lower()
            category_map = {
                "bug": IssueCategory.BUG,
                "security": IssueCategory.SECURITY,
                "performance": IssueCategory.PERFORMANCE,
                "code_smell": IssueCategory.CODE_SMELL,
                "error_handling": IssueCategory.ERROR_HANDLING,
                "validation": IssueCategory.VALIDATION,
                "hardcoded": IssueCategory.HARDCODED,
                "deprecated": IssueCategory.DEPRECATED,
            }
            category = category_map.get(category_str, IssueCategory.CODE_SMELL)

            # Generate unique ID
            issue_id = self._generate_id(file_path, title, item.get("line"))

            return CodeIssue(
                id=issue_id,
                file=file_path,
                line=item.get("line"),
                severity=severity,
                category=category,
                title=title[:80],  # Truncate long titles
                description=item.get("description", title),
                suggested_fix=item.get("suggested_fix"),
            )

        except (KeyError, ValueError, TypeError):
            return None

    def _get_reviewable_files(self, max_files: int) -> list[Path]:
        """Get list of files to review.

        Args:
            max_files: Maximum number of files to return.

        Returns:
            List of file paths.
        """
        files = []

        for file_path in self.project_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Check extension
            if file_path.suffix.lower() not in REVIEWABLE_EXTENSIONS:
                continue

            # Skip excluded directories
            skip = False
            for part in file_path.parts:
                if part in SKIP_DIRECTORIES or part.startswith("."):
                    skip = True
                    break
            if skip:
                continue

            # Skip test files (they're analyzed separately)
            name_lower = file_path.name.lower()
            if "test" in name_lower or "spec" in name_lower:
                continue

            # Skip very small files
            try:
                if file_path.stat().st_size < 100:
                    continue
            except OSError:
                continue

            files.append(file_path)

            if len(files) >= max_files:
                break

        # Sort by size (larger files first - more likely to have issues)
        files.sort(key=lambda f: f.stat().st_size, reverse=True)

        return files[:max_files]

    def _generate_id(
        self,
        file_path: str,
        title: str,
        line: int | None,
    ) -> str:
        """Generate a unique ID for an issue.

        Args:
            file_path: File path.
            title: Issue title.
            line: Line number.

        Returns:
            Unique ID string.
        """
        hash_input = f"{self.project_path}:{file_path}:{title}:{line or 0}"
        return f"cr-{hashlib.md5(hash_input.encode()).hexdigest()[:12]}"
