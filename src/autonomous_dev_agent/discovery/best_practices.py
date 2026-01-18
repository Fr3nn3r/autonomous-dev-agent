"""Best practices checker for project discovery.

Checks for common best practices like linting, type checking, testing, and documentation.
"""

import hashlib
from pathlib import Path

from ..models import BestPracticeViolation, Severity


# Linter configuration files by language
LINTER_CONFIGS: dict[str, list[str]] = {
    "python": [
        "ruff.toml", ".ruff.toml", "pyproject.toml",  # ruff config can be in pyproject.toml
        ".flake8", "setup.cfg",  # flake8
        ".pylintrc", "pylintrc", "pyproject.toml",  # pylint
    ],
    "javascript": [
        ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
        "eslint.config.js", "eslint.config.mjs",
    ],
    "typescript": [
        ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
        "eslint.config.js", "eslint.config.mjs",
    ],
    "rust": ["rustfmt.toml", ".rustfmt.toml", "clippy.toml"],
    "go": [".golangci.yml", ".golangci.yaml", "golangci.yml"],
}

# Type checker configuration files
TYPE_CHECKER_CONFIGS: dict[str, list[str]] = {
    "python": [
        "pyrightconfig.json", "pyproject.toml",  # pyright
        "mypy.ini", ".mypy.ini", "pyproject.toml", "setup.cfg",  # mypy
    ],
    "typescript": ["tsconfig.json"],
}

# Test framework indicators
TEST_FRAMEWORK_INDICATORS: dict[str, list[str]] = {
    "python": ["pytest.ini", "pyproject.toml", "conftest.py", "tests/", "test/"],
    "javascript": ["jest.config.js", "jest.config.ts", "vitest.config.js", "vitest.config.ts", "__tests__/"],
    "typescript": ["jest.config.js", "jest.config.ts", "vitest.config.js", "vitest.config.ts", "__tests__/"],
    "rust": ["tests/"],
    "go": ["_test.go"],
}

# Documentation indicators
DOCUMENTATION_INDICATORS: list[str] = [
    "README.md", "README.rst", "README.txt", "README",
    "docs/", "doc/", "documentation/",
    "CONTRIBUTING.md", "CHANGELOG.md", "CHANGES.md",
]

# Git-related files
GIT_INDICATORS: list[str] = [
    ".git/",
    ".gitignore",
    ".gitattributes",
]

# CI/CD configuration files
CI_CD_CONFIGS: list[str] = [
    ".github/workflows/",  # GitHub Actions
    ".gitlab-ci.yml",  # GitLab CI
    "Jenkinsfile",  # Jenkins
    ".circleci/config.yml",  # CircleCI
    ".travis.yml",  # Travis CI
    "azure-pipelines.yml",  # Azure DevOps
    "bitbucket-pipelines.yml",  # Bitbucket Pipelines
]

# Security-related files
SECURITY_INDICATORS: list[str] = [
    ".env.example",  # Environment template
    ".gitignore",  # Should ignore sensitive files
    "SECURITY.md",
]


class BestPracticesChecker:
    """Checks for best practices in a project."""

    def __init__(self, project_path: Path | str, languages: list[str] | None = None):
        """Initialize the checker.

        Args:
            project_path: Path to the project root directory.
            languages: List of detected languages (optional, for targeted checks).
        """
        self.project_path = Path(project_path).resolve()
        self.languages = languages or []

    def check_all(self) -> list[BestPracticeViolation]:
        """Run all best practice checks.

        Returns:
            List of violations found.
        """
        violations = []
        violations.extend(self.check_linter())
        violations.extend(self.check_type_checker())
        violations.extend(self.check_test_framework())
        violations.extend(self.check_documentation())
        violations.extend(self.check_git())
        violations.extend(self.check_ci_cd())
        violations.extend(self.check_security())
        violations.extend(self.check_editorconfig())
        violations.extend(self.check_license())
        return violations

    def check_linter(self) -> list[BestPracticeViolation]:
        """Check for linter configuration.

        Returns:
            List of violations if no linter is configured.
        """
        violations = []

        # Check each detected language
        languages_to_check = self.languages if self.languages else list(LINTER_CONFIGS.keys())

        for language in languages_to_check:
            if language not in LINTER_CONFIGS:
                continue

            # Check if any linter config exists
            has_linter = False
            for config_file in LINTER_CONFIGS[language]:
                if self._exists(config_file):
                    # For pyproject.toml, verify it has linter config
                    if config_file == "pyproject.toml" and language == "python":
                        content = self._read_file("pyproject.toml")
                        if content and ("[tool.ruff]" in content or "[tool.pylint]" in content
                                        or "[tool.flake8]" in content):
                            has_linter = True
                            break
                    else:
                        has_linter = True
                        break

            if not has_linter:
                violations.append(BestPracticeViolation(
                    id=self._generate_id(f"no-linter-{language}"),
                    category="linting",
                    severity=Severity.MEDIUM,
                    title=f"No linter configured for {language}",
                    description=f"No linter configuration found for {language} code. "
                                "Linters help catch bugs and enforce code style.",
                    recommendation=self._get_linter_recommendation(language),
                ))

        return violations

    def check_type_checker(self) -> list[BestPracticeViolation]:
        """Check for type checking configuration.

        Returns:
            List of violations if no type checker is configured.
        """
        violations = []

        languages_to_check = self.languages if self.languages else list(TYPE_CHECKER_CONFIGS.keys())

        for language in languages_to_check:
            if language not in TYPE_CHECKER_CONFIGS:
                continue

            has_type_checker = False
            for config_file in TYPE_CHECKER_CONFIGS[language]:
                if self._exists(config_file):
                    if config_file == "pyproject.toml":
                        content = self._read_file("pyproject.toml")
                        if content and ("[tool.pyright]" in content or "[tool.mypy]" in content):
                            has_type_checker = True
                            break
                    else:
                        has_type_checker = True
                        break

            if not has_type_checker:
                violations.append(BestPracticeViolation(
                    id=self._generate_id(f"no-type-checker-{language}"),
                    category="typing",
                    severity=Severity.LOW,
                    title=f"No type checker configured for {language}",
                    description=f"No type checking configuration found for {language}. "
                                "Type checking helps catch bugs at development time.",
                    recommendation=self._get_type_checker_recommendation(language),
                ))

        return violations

    def check_test_framework(self) -> list[BestPracticeViolation]:
        """Check for test framework configuration.

        Returns:
            List of violations if no test framework is found.
        """
        violations = []

        languages_to_check = self.languages if self.languages else list(TEST_FRAMEWORK_INDICATORS.keys())

        for language in languages_to_check:
            if language not in TEST_FRAMEWORK_INDICATORS:
                continue

            has_tests = False
            for indicator in TEST_FRAMEWORK_INDICATORS[language]:
                if indicator.endswith("/"):
                    # Check for directory
                    if (self.project_path / indicator.rstrip("/")).is_dir():
                        has_tests = True
                        break
                elif indicator.endswith(".go"):
                    # Special case for Go test files
                    test_files = list(self.project_path.rglob("*_test.go"))
                    if test_files:
                        has_tests = True
                        break
                elif self._exists(indicator):
                    if indicator == "pyproject.toml":
                        content = self._read_file("pyproject.toml")
                        if content and "[tool.pytest" in content:
                            has_tests = True
                            break
                    else:
                        has_tests = True
                        break

            if not has_tests:
                violations.append(BestPracticeViolation(
                    id=self._generate_id(f"no-test-framework-{language}"),
                    category="testing",
                    severity=Severity.HIGH,
                    title=f"No test framework found for {language}",
                    description=f"No test framework configuration or test directory found for {language}. "
                                "Tests are essential for maintaining code quality.",
                    recommendation=self._get_test_framework_recommendation(language),
                ))

        return violations

    def check_documentation(self) -> list[BestPracticeViolation]:
        """Check for documentation.

        Returns:
            List of violations if documentation is missing.
        """
        violations = []

        # Check for README
        has_readme = False
        for readme in ["README.md", "README.rst", "README.txt", "README"]:
            if self._exists(readme):
                has_readme = True
                break

        if not has_readme:
            violations.append(BestPracticeViolation(
                id=self._generate_id("no-readme"),
                category="documentation",
                severity=Severity.HIGH,
                title="No README file",
                description="No README file found. A README helps others understand your project.",
                recommendation="Create a README.md with project description, installation, and usage instructions.",
            ))

        # Check for CONTRIBUTING guide in larger projects
        has_contributing = self._exists("CONTRIBUTING.md") or self._exists("CONTRIBUTING")
        code_files = list(self.project_path.rglob("*.py")) + list(self.project_path.rglob("*.js"))
        is_large_project = len(code_files) > 20

        if is_large_project and not has_contributing:
            violations.append(BestPracticeViolation(
                id=self._generate_id("no-contributing"),
                category="documentation",
                severity=Severity.LOW,
                title="No CONTRIBUTING guide",
                description="No CONTRIBUTING.md found. For larger projects, this helps new contributors.",
                recommendation="Create a CONTRIBUTING.md with guidelines for contributing to the project.",
            ))

        return violations

    def check_git(self) -> list[BestPracticeViolation]:
        """Check for Git configuration.

        Returns:
            List of violations if Git is not properly configured.
        """
        violations = []

        # Check for .git directory
        if not (self.project_path / ".git").is_dir():
            violations.append(BestPracticeViolation(
                id=self._generate_id("no-git"),
                category="version_control",
                severity=Severity.HIGH,
                title="Not a Git repository",
                description="This directory is not a Git repository. Version control is essential.",
                recommendation="Initialize Git with 'git init' and create an initial commit.",
            ))
            return violations  # No point checking other git files

        # Check for .gitignore
        if not self._exists(".gitignore"):
            violations.append(BestPracticeViolation(
                id=self._generate_id("no-gitignore"),
                category="version_control",
                severity=Severity.MEDIUM,
                title="No .gitignore file",
                description="No .gitignore file found. This may lead to committing sensitive or unnecessary files.",
                recommendation="Create a .gitignore file appropriate for your project's languages and tools.",
            ))

        return violations

    def check_ci_cd(self) -> list[BestPracticeViolation]:
        """Check for CI/CD configuration.

        Returns:
            List of violations if no CI/CD is configured.
        """
        violations = []

        has_ci = False
        for config in CI_CD_CONFIGS:
            if config.endswith("/"):
                if (self.project_path / config.rstrip("/")).is_dir():
                    has_ci = True
                    break
            elif self._exists(config):
                has_ci = True
                break

        if not has_ci:
            violations.append(BestPracticeViolation(
                id=self._generate_id("no-ci-cd"),
                category="ci_cd",
                severity=Severity.MEDIUM,
                title="No CI/CD configuration",
                description="No CI/CD configuration found. Automated testing and deployment improves reliability.",
                recommendation="Set up CI/CD with GitHub Actions, GitLab CI, or another provider.",
            ))

        return violations

    def check_security(self) -> list[BestPracticeViolation]:
        """Check for security best practices.

        Returns:
            List of violations if security practices are missing.
        """
        violations = []

        # Check for .env.example when .env might be used
        has_env_example = self._exists(".env.example") or self._exists(".env.template")
        gitignore_content = self._read_file(".gitignore") or ""

        # Check if .env is likely used but not gitignored
        if not has_env_example and ".env" not in gitignore_content:
            # Check if project likely uses environment variables
            package_json = self._read_file("package.json")
            pyproject = self._read_file("pyproject.toml")
            if (package_json and "dotenv" in package_json) or (pyproject and "python-dotenv" in pyproject):
                violations.append(BestPracticeViolation(
                    id=self._generate_id("no-env-example"),
                    category="security",
                    severity=Severity.MEDIUM,
                    title="No .env.example file",
                    description="Project uses dotenv but has no .env.example template. "
                                "This helps developers know what environment variables are needed.",
                    recommendation="Create a .env.example file with placeholder values for required environment variables.",
                ))

        # Check if common sensitive patterns are in gitignore
        sensitive_patterns = [".env", "*.key", "*.pem", "credentials"]
        missing_patterns = []
        for pattern in sensitive_patterns:
            if pattern not in gitignore_content:
                missing_patterns.append(pattern)

        if missing_patterns and gitignore_content:  # Only if gitignore exists
            violations.append(BestPracticeViolation(
                id=self._generate_id("gitignore-security"),
                category="security",
                severity=Severity.LOW,
                title="Potentially sensitive files not in .gitignore",
                description=f"Consider adding these patterns to .gitignore: {', '.join(missing_patterns)}",
                recommendation="Add common sensitive file patterns to .gitignore to prevent accidental commits.",
            ))

        return violations

    def check_editorconfig(self) -> list[BestPracticeViolation]:
        """Check for EditorConfig.

        Returns:
            List of violations if EditorConfig is missing.
        """
        violations = []

        if not self._exists(".editorconfig"):
            violations.append(BestPracticeViolation(
                id=self._generate_id("no-editorconfig"),
                category="consistency",
                severity=Severity.LOW,
                title="No .editorconfig file",
                description="No .editorconfig found. EditorConfig helps maintain consistent formatting across editors.",
                recommendation="Create an .editorconfig file to define consistent indentation and line endings.",
            ))

        return violations

    def check_license(self) -> list[BestPracticeViolation]:
        """Check for license file.

        Returns:
            List of violations if license is missing.
        """
        violations = []

        has_license = False
        for license_file in ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"]:
            if self._exists(license_file):
                has_license = True
                break

        if not has_license:
            violations.append(BestPracticeViolation(
                id=self._generate_id("no-license"),
                category="legal",
                severity=Severity.MEDIUM,
                title="No LICENSE file",
                description="No license file found. Without a license, the code is copyrighted by default.",
                recommendation="Add a LICENSE file to clarify how others can use your code.",
            ))

        return violations

    def _exists(self, path: str) -> bool:
        """Check if a file or directory exists.

        Args:
            path: Relative path to check.

        Returns:
            True if the path exists.
        """
        return (self.project_path / path).exists()

    def _read_file(self, path: str) -> str | None:
        """Read a file's contents.

        Args:
            path: Relative path to the file.

        Returns:
            File contents or None if not readable.
        """
        try:
            return (self.project_path / path).read_text(encoding="utf-8", errors="ignore")
        except (OSError, IOError):
            return None

    def _generate_id(self, base: str) -> str:
        """Generate a unique ID for a violation.

        Args:
            base: Base string for the ID.

        Returns:
            Unique ID string.
        """
        project_hash = hashlib.md5(str(self.project_path).encode()).hexdigest()[:8]
        return f"bp-{base}-{project_hash}"

    def _get_linter_recommendation(self, language: str) -> str:
        """Get linter recommendation for a language."""
        recommendations = {
            "python": "Install and configure ruff: 'pip install ruff' and create ruff.toml",
            "javascript": "Install and configure ESLint: 'npm install eslint' and run 'npx eslint --init'",
            "typescript": "Install and configure ESLint: 'npm install eslint' and run 'npx eslint --init'",
            "rust": "Rustfmt and Clippy are included with Rust. Run 'cargo fmt' and 'cargo clippy'",
            "go": "Install golangci-lint: 'go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest'",
        }
        return recommendations.get(language, "Configure a linter for your language")

    def _get_type_checker_recommendation(self, language: str) -> str:
        """Get type checker recommendation for a language."""
        recommendations = {
            "python": "Install pyright: 'pip install pyright' or configure mypy in pyproject.toml",
            "typescript": "TypeScript includes type checking. Ensure tsconfig.json has strict mode enabled.",
        }
        return recommendations.get(language, "Configure type checking for your language")

    def _get_test_framework_recommendation(self, language: str) -> str:
        """Get test framework recommendation for a language."""
        recommendations = {
            "python": "Install pytest: 'pip install pytest' and create a tests/ directory",
            "javascript": "Install Jest or Vitest: 'npm install jest' or 'npm install vitest'",
            "typescript": "Install Jest or Vitest with TypeScript support",
            "rust": "Rust has built-in testing. Create a tests/ directory or add #[test] functions",
            "go": "Go has built-in testing. Create *_test.go files with Test* functions",
        }
        return recommendations.get(language, "Set up a test framework for your language")
