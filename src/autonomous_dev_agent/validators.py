"""Quality gate validation engine.

Runs configured quality checks before marking a feature as complete.
Helps prevent common issues like missing tests, bloated files, and lint errors.
"""

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .models import Feature, QualityGates


class ValidationSeverity(str, Enum):
    """Severity level for validation results."""
    ERROR = "error"      # Blocks completion
    WARNING = "warning"  # Logged but doesn't block


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    name: str
    passed: bool
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    details: Optional[str] = None


@dataclass
class ValidationReport:
    """Aggregated results from all validation checks."""
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Check if all error-severity validations passed."""
        return all(
            r.passed for r in self.results
            if r.severity == ValidationSeverity.ERROR
        )

    @property
    def error_count(self) -> int:
        """Count of failed error-severity validations."""
        return sum(
            1 for r in self.results
            if not r.passed and r.severity == ValidationSeverity.ERROR
        )

    @property
    def warning_count(self) -> int:
        """Count of failed warning-severity validations."""
        return sum(
            1 for r in self.results
            if not r.passed and r.severity == ValidationSeverity.WARNING
        )


class QualityGateValidator:
    """Validates quality gates for a feature.

    Runs all configured checks and returns a comprehensive report.
    """

    # File extensions to check for max_file_lines
    SOURCE_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".svelte",
        ".java", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
        ".rb", ".php", ".swift", ".kt", ".scala"
    }

    def __init__(self, project_path: Path | str):
        self.project_path = Path(project_path)

    def validate(
        self,
        feature: Feature,
        default_gates: Optional[QualityGates] = None
    ) -> ValidationReport:
        """Run all quality gate validations for a feature.

        Args:
            feature: The feature being validated
            default_gates: Default quality gates from config

        Returns:
            ValidationReport with all check results
        """
        report = ValidationReport()

        # Merge feature gates with defaults
        gates = self._merge_gates(feature.quality_gates, default_gates)

        if not gates:
            # No quality gates configured
            return report

        # Run lint command if configured
        if gates.lint_command:
            result = self._run_command_validator("Lint", gates.lint_command)
            report.results.append(result)

        # Run type check command if configured
        if gates.type_check_command:
            result = self._run_command_validator("Type Check", gates.type_check_command)
            report.results.append(result)

        # Check file sizes if configured
        if gates.max_file_lines:
            result = self._check_file_sizes(gates.max_file_lines)
            report.results.append(result)

        # Run custom validators
        for i, cmd in enumerate(gates.custom_validators):
            result = self._run_command_validator(f"Custom Validator {i+1}", cmd)
            report.results.append(result)

        return report

    def _merge_gates(
        self,
        feature_gates: Optional[QualityGates],
        default_gates: Optional[QualityGates]
    ) -> Optional[QualityGates]:
        """Merge feature-specific gates with defaults.

        Feature gates take precedence. If a field is not set on feature gates,
        the default value is used.

        Args:
            feature_gates: Quality gates from the feature
            default_gates: Default quality gates from config

        Returns:
            Merged QualityGates or None if neither is set
        """
        if not feature_gates and not default_gates:
            return None

        if not default_gates:
            return feature_gates

        if not feature_gates:
            return default_gates

        # Merge: feature overrides defaults
        return QualityGates(
            require_tests=feature_gates.require_tests or default_gates.require_tests,
            max_file_lines=feature_gates.max_file_lines or default_gates.max_file_lines,
            security_checklist=(
                feature_gates.security_checklist
                if feature_gates.security_checklist
                else default_gates.security_checklist
            ),
            lint_command=feature_gates.lint_command or default_gates.lint_command,
            type_check_command=(
                feature_gates.type_check_command or default_gates.type_check_command
            ),
            custom_validators=(
                feature_gates.custom_validators
                if feature_gates.custom_validators
                else default_gates.custom_validators
            )
        )

    def _run_command_validator(self, name: str, command: str) -> ValidationResult:
        """Run a shell command and check its exit code.

        Args:
            name: Human-readable name for the check
            command: Shell command to execute

        Returns:
            ValidationResult indicating pass/fail
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if result.returncode == 0:
                return ValidationResult(
                    name=name,
                    passed=True,
                    message="Passed"
                )
            else:
                # Combine stdout and stderr, truncate if too long
                output = (result.stdout + result.stderr).strip()
                if len(output) > 500:
                    output = output[:500] + "\n... (truncated)"

                return ValidationResult(
                    name=name,
                    passed=False,
                    message=f"Failed (exit code {result.returncode})",
                    details=output
                )

        except subprocess.TimeoutExpired:
            return ValidationResult(
                name=name,
                passed=False,
                message="Timed out after 120 seconds"
            )
        except Exception as e:
            return ValidationResult(
                name=name,
                passed=False,
                message=f"Error running command: {e}"
            )

    def _check_file_sizes(self, max_lines: int) -> ValidationResult:
        """Check that no source files exceed the maximum line count.

        Args:
            max_lines: Maximum allowed lines per file

        Returns:
            ValidationResult with list of violations in details
        """
        violations: list[str] = []

        # Walk through source files
        for ext in self.SOURCE_EXTENSIONS:
            for file_path in self.project_path.rglob(f"*{ext}"):
                # Skip common directories
                if any(part.startswith('.') or part in ('node_modules', '__pycache__', 'venv', '.venv', 'dist', 'build')
                       for part in file_path.parts):
                    continue

                try:
                    line_count = len(file_path.read_text(encoding="utf-8").splitlines())
                    if line_count > max_lines:
                        rel_path = file_path.relative_to(self.project_path)
                        violations.append(f"{rel_path}: {line_count} lines (max: {max_lines})")
                except (UnicodeDecodeError, PermissionError):
                    # Skip files we can't read
                    continue

        if violations:
            return ValidationResult(
                name="File Size Check",
                passed=False,
                message=f"{len(violations)} file(s) exceed {max_lines} lines",
                details="\n".join(violations[:10])  # Show first 10
            )

        return ValidationResult(
            name="File Size Check",
            passed=True,
            message=f"All source files under {max_lines} lines"
        )
