"""Specification file parser for AI-driven feature generation.

Parses application specification files (txt, md, spec) for use in
generating feature backlogs with Claude AI.
"""

from dataclasses import dataclass
from pathlib import Path


# Supported specification file extensions
SUPPORTED_EXTENSIONS: set[str] = {".txt", ".md", ".spec", ".markdown"}

# Minimum content length for a valid spec (characters)
MIN_CONTENT_LENGTH = 100

# Maximum content length to send to Claude (characters)
MAX_CONTENT_LENGTH = 100000


@dataclass
class ParsedSpec:
    """Result of parsing a specification file."""

    file_path: Path
    content: str
    title: str | None
    sections: dict[str, str]
    word_count: int

    @property
    def is_valid(self) -> bool:
        """Check if the parsed spec meets minimum requirements."""
        return len(self.content) >= MIN_CONTENT_LENGTH

    def get_truncated_content(self, max_length: int = MAX_CONTENT_LENGTH) -> str:
        """Get content truncated to max length if needed."""
        if len(self.content) <= max_length:
            return self.content

        # Truncate with notice
        truncated = self.content[:max_length]
        # Try to truncate at a sentence boundary
        last_period = truncated.rfind(".")
        if last_period > max_length * 0.8:
            truncated = truncated[:last_period + 1]

        return truncated + "\n\n[Content truncated due to length...]"


class SpecParser:
    """Parser for application specification files."""

    def __init__(self, spec_path: Path | str):
        """Initialize the parser.

        Args:
            spec_path: Path to the specification file.

        Raises:
            FileNotFoundError: If the spec file doesn't exist.
            ValueError: If the file extension is not supported.
        """
        self.spec_path = Path(spec_path).resolve()

        if not self.spec_path.exists():
            raise FileNotFoundError(f"Specification file not found: {self.spec_path}")

        if not self.spec_path.is_file():
            raise ValueError(f"Path is not a file: {self.spec_path}")

        suffix = self.spec_path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension: {suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

    def parse(self) -> ParsedSpec:
        """Parse the specification file.

        Returns:
            ParsedSpec with the parsed content and metadata.

        Raises:
            ValueError: If the file content is too short.
        """
        content = self.spec_path.read_text(encoding="utf-8")

        # Basic content validation
        if len(content.strip()) < MIN_CONTENT_LENGTH:
            raise ValueError(
                f"Specification file too short ({len(content.strip())} chars). "
                f"Minimum required: {MIN_CONTENT_LENGTH} characters."
            )

        # Extract title from first heading or first line
        title = self._extract_title(content)

        # Extract sections if markdown
        sections = {}
        if self.spec_path.suffix.lower() in {".md", ".markdown"}:
            sections = self._extract_markdown_sections(content)

        # Count words
        word_count = len(content.split())

        return ParsedSpec(
            file_path=self.spec_path,
            content=content,
            title=title,
            sections=sections,
            word_count=word_count,
        )

    def _extract_title(self, content: str) -> str | None:
        """Extract title from content.

        Looks for:
        1. First # heading in markdown
        2. First line if it looks like a title

        Args:
            content: File content.

        Returns:
            Extracted title or None.
        """
        lines = content.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Markdown heading
            if line.startswith("# "):
                return line[2:].strip()

            # First non-empty line as title if it's short enough
            if len(line) < 100 and not line.startswith("-") and not line.startswith("*"):
                return line

            break

        return None

    def _extract_markdown_sections(self, content: str) -> dict[str, str]:
        """Extract sections from markdown content.

        Args:
            content: Markdown content.

        Returns:
            Dictionary mapping section titles to their content.
        """
        sections: dict[str, str] = {}
        current_section: str | None = None
        current_content: list[str] = []

        for line in content.split("\n"):
            # Check for heading (## or ### level)
            if line.startswith("## ") or line.startswith("### "):
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                # Start new section
                current_section = line.lstrip("#").strip()
                current_content = []
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    @staticmethod
    def validate_path(path: Path | str) -> tuple[bool, str]:
        """Validate a potential spec file path.

        Args:
            path: Path to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        path = Path(path)

        if not path.exists():
            return False, f"File not found: {path}"

        if not path.is_file():
            return False, f"Path is not a file: {path}"

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            return False, (
                f"Unsupported extension: {suffix}. "
                f"Use one of: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        try:
            content = path.read_text(encoding="utf-8")
            if len(content.strip()) < MIN_CONTENT_LENGTH:
                return False, (
                    f"File too short ({len(content.strip())} chars). "
                    f"Need at least {MIN_CONTENT_LENGTH} characters."
                )
        except UnicodeDecodeError:
            return False, "File is not valid UTF-8 text"
        except OSError as e:
            return False, f"Cannot read file: {e}"

        return True, ""
