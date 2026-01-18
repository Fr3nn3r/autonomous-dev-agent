"""Test gap analyzer for project discovery.

Identifies modules and files that lack test coverage.
"""

import hashlib
import re
from pathlib import Path
from typing import Literal

from ..models import Severity, TestGap


# Test file naming conventions by language
TEST_FILE_PATTERNS: dict[str, list[str]] = {
    "python": [
        "test_{name}.py",      # pytest convention
        "{name}_test.py",      # alternate convention
        "tests/test_{name}.py",
        "tests/{name}_test.py",
        "test/{name}.py",
    ],
    "javascript": [
        "{name}.test.js",
        "{name}.spec.js",
        "__tests__/{name}.test.js",
        "__tests__/{name}.js",
        "tests/{name}.test.js",
    ],
    "typescript": [
        "{name}.test.ts",
        "{name}.spec.ts",
        "{name}.test.tsx",
        "{name}.spec.tsx",
        "__tests__/{name}.test.ts",
        "__tests__/{name}.ts",
        "tests/{name}.test.ts",
    ],
    "rust": [
        "tests/{name}.rs",
        # Rust also has inline tests with #[test]
    ],
    "go": [
        "{name}_test.go",
    ],
    "java": [
        "{name}Test.java",
        "test/{path}/{name}Test.java",
        "src/test/java/{path}/{name}Test.java",
    ],
}

# Critical path indicators - files/modules that should definitely have tests
CRITICAL_PATH_INDICATORS: list[str] = [
    "auth",
    "authentication",
    "authorization",
    "payment",
    "billing",
    "checkout",
    "security",
    "encryption",
    "password",
    "credential",
    "api",
    "database",
    "db",
    "migration",
    "transaction",
    "order",
    "user",
    "account",
    "session",
    "token",
]

# Directories typically excluded from test coverage analysis
EXCLUDED_FROM_COVERAGE: set[str] = {
    "node_modules",
    "__pycache__",
    ".git",
    "venv",
    ".venv",
    "dist",
    "build",
    "target",
    ".tox",
    ".pytest_cache",
    "migrations",  # Database migrations often don't need direct tests
    "scripts",     # One-off scripts
    "docs",
    "examples",
}


class TestGapAnalyzer:
    """Analyzes test coverage gaps in a project."""

    def __init__(self, project_path: Path | str, languages: list[str] | None = None):
        """Initialize the analyzer.

        Args:
            project_path: Path to the project root directory.
            languages: List of detected languages (for targeted analysis).
        """
        self.project_path = Path(project_path).resolve()
        self.languages = languages or []
        self._test_file_cache: set[str] | None = None

    def analyze(self) -> list[TestGap]:
        """Analyze test coverage and find gaps.

        Returns:
            List of TestGap objects representing coverage gaps.
        """
        gaps = []

        # Build cache of test files
        self._build_test_file_cache()

        # Analyze each supported language
        for language in self._get_languages_to_analyze():
            gaps.extend(self._analyze_language(language))

        return gaps

    def _get_languages_to_analyze(self) -> list[str]:
        """Get list of languages to analyze.

        Returns:
            List of language names.
        """
        if self.languages:
            return [lang for lang in self.languages if lang in TEST_FILE_PATTERNS]

        # Auto-detect based on file extensions
        detected = []
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
        }

        for ext, lang in extension_map.items():
            pattern = f"*{ext}"
            if any(self.project_path.rglob(pattern)):
                if lang not in detected:
                    detected.append(lang)

        return detected

    def _build_test_file_cache(self) -> None:
        """Build a cache of all test file paths."""
        self._test_file_cache = set()

        test_patterns = [
            "**/test_*.py", "**/*_test.py",
            "**/*.test.js", "**/*.spec.js",
            "**/*.test.ts", "**/*.spec.ts", "**/*.test.tsx", "**/*.spec.tsx",
            "**/tests/*.rs",
            "**/*_test.go",
            "**/*Test.java",
        ]

        for pattern in test_patterns:
            for test_file in self.project_path.rglob(pattern):
                if not self._should_exclude(test_file):
                    # Normalize path for comparison (use forward slashes for cross-platform)
                    relative = str(test_file.relative_to(self.project_path))
                    normalized = relative.replace("\\", "/").lower()
                    self._test_file_cache.add(normalized)

    def _analyze_language(self, language: str) -> list[TestGap]:
        """Analyze test coverage for a specific language.

        Args:
            language: The programming language to analyze.

        Returns:
            List of test gaps found.
        """
        gaps = []
        source_files = self._get_source_files(language)

        for source_file in source_files:
            gap = self._check_file_coverage(source_file, language)
            if gap:
                gaps.append(gap)

        return gaps

    def _get_source_files(self, language: str) -> list[Path]:
        """Get all source files for a language (excluding tests).

        Args:
            language: The programming language.

        Returns:
            List of source file paths.
        """
        extension_map = {
            "python": ["*.py"],
            "javascript": ["*.js", "*.mjs"],
            "typescript": ["*.ts", "*.tsx"],
            "rust": ["*.rs"],
            "go": ["*.go"],
            "java": ["*.java"],
        }

        extensions = extension_map.get(language, [])
        source_files = []

        for ext in extensions:
            for file_path in self.project_path.rglob(ext):
                if self._should_exclude(file_path):
                    continue

                # Skip test files
                if self._is_test_file(file_path, language):
                    continue

                # Skip __init__.py (usually don't need dedicated tests)
                if file_path.name == "__init__.py":
                    continue

                # Skip setup.py, conftest.py, etc.
                if file_path.name in {"setup.py", "conftest.py", "manage.py"}:
                    continue

                source_files.append(file_path)

        return source_files

    def _is_test_file(self, file_path: Path, language: str) -> bool:
        """Check if a file is a test file.

        Args:
            file_path: Path to check.
            language: Programming language.

        Returns:
            True if the file is a test file.
        """
        name = file_path.name.lower()
        relative_path = str(file_path.relative_to(self.project_path)).lower()

        # Common test patterns
        test_indicators = [
            "test_", "_test.", ".test.", ".spec.",
            "/tests/", "/test/", "/__tests__/",
            "test.py", "tests.py",
        ]

        # Go-specific pattern
        if language == "go" and name.endswith("_test.go"):
            return True

        for indicator in test_indicators:
            if indicator in name or indicator in relative_path:
                return True

        return False

    def _check_file_coverage(self, source_file: Path, language: str) -> TestGap | None:
        """Check if a source file has corresponding tests.

        Args:
            source_file: Path to the source file.
            language: Programming language.

        Returns:
            TestGap if no tests found, None otherwise.
        """
        relative_path = source_file.relative_to(self.project_path)
        name_without_ext = source_file.stem
        parent_dir = relative_path.parent

        # Check for inline tests (Rust)
        if language == "rust":
            if self._has_inline_tests(source_file):
                return None

        # Check all potential test file locations
        patterns = TEST_FILE_PATTERNS.get(language, [])
        for pattern in patterns:
            # Format the pattern with the module name
            test_path = pattern.format(
                name=name_without_ext,
                path=str(parent_dir).replace("\\", "/"),
            )

            # Normalize to forward slashes for cross-platform comparison
            normalized_test_path = test_path.replace("\\", "/").lower()

            # Check if test file exists
            if normalized_test_path in self._test_file_cache:
                return None

            # Also check relative to the source file's directory
            relative_test_path = str(parent_dir / test_path).replace("\\", "/").lower()
            if relative_test_path in self._test_file_cache:
                return None

        # No test found - create a gap
        is_critical = self._is_critical_path(source_file)
        gap_type = self._determine_gap_type(source_file, language)

        return TestGap(
            id=self._generate_id(str(relative_path)),
            module=str(relative_path),
            gap_type=gap_type,
            severity=Severity.HIGH if is_critical else Severity.MEDIUM,
            is_critical_path=is_critical,
            description=self._generate_description(relative_path, is_critical, gap_type),
        )

    def _has_inline_tests(self, file_path: Path) -> bool:
        """Check if a file has inline tests (for Rust).

        Args:
            file_path: Path to the source file.

        Returns:
            True if the file has inline tests.
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            # Check for Rust test attributes
            if "#[test]" in content or "#[cfg(test)]" in content:
                return True
        except (OSError, IOError):
            pass
        return False

    def _is_critical_path(self, file_path: Path) -> bool:
        """Check if a file is in a critical code path.

        Args:
            file_path: Path to check.

        Returns:
            True if the file is in a critical path.
        """
        name_lower = file_path.name.lower()
        path_lower = str(file_path).lower()

        for indicator in CRITICAL_PATH_INDICATORS:
            if indicator in name_lower or indicator in path_lower:
                return True

        return False

    def _determine_gap_type(
        self,
        source_file: Path,
        language: str,
    ) -> Literal["no_tests", "partial_coverage", "missing_edge_cases"]:
        """Determine the type of test gap.

        Args:
            source_file: Path to the source file.
            language: Programming language.

        Returns:
            Type of test gap.
        """
        # For now, we assume no tests if no test file is found
        # Future enhancement: use coverage data if available
        return "no_tests"

    def _generate_description(
        self,
        relative_path: Path,
        is_critical: bool,
        gap_type: Literal["no_tests", "partial_coverage", "missing_edge_cases"],
    ) -> str:
        """Generate a description for the test gap.

        Args:
            relative_path: Relative path to the file.
            is_critical: Whether the file is in a critical path.
            gap_type: Type of test gap.

        Returns:
            Description string.
        """
        descriptions = {
            "no_tests": f"No test file found for {relative_path}",
            "partial_coverage": f"Partial test coverage for {relative_path}",
            "missing_edge_cases": f"Missing edge case tests for {relative_path}",
        }

        desc = descriptions.get(gap_type, f"Test gap for {relative_path}")

        if is_critical:
            desc += ". This is a critical code path and should be prioritized."

        return desc

    def _should_exclude(self, file_path: Path) -> bool:
        """Check if a file should be excluded from analysis.

        Args:
            file_path: Path to check.

        Returns:
            True if the file should be excluded.
        """
        for part in file_path.parts:
            if part in EXCLUDED_FROM_COVERAGE:
                return True
            # Skip hidden directories
            if part.startswith(".") and part not in {"."}:
                return True
        return False

    def _generate_id(self, base: str) -> str:
        """Generate a unique ID for a test gap.

        Args:
            base: Base string for the ID.

        Returns:
            Unique ID string.
        """
        hash_input = f"{self.project_path}:{base}"
        return f"tg-{hashlib.md5(hash_input.encode()).hexdigest()[:12]}"
