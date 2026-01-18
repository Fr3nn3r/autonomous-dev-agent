"""Tests for the quality gate validators."""

import pytest
from pathlib import Path
import tempfile
import os

from autonomous_dev_agent.models import Feature, QualityGates
from autonomous_dev_agent.validators import (
    ValidationResult,
    ValidationReport,
    ValidationSeverity,
    QualityGateValidator
)


class TestValidationResult:
    def test_create_passing_result(self):
        result = ValidationResult(
            name="Test Check",
            passed=True,
            message="All good"
        )
        assert result.passed is True
        assert result.severity == ValidationSeverity.ERROR

    def test_create_failing_result(self):
        result = ValidationResult(
            name="Lint",
            passed=False,
            message="3 errors found",
            details="line 10: unused import"
        )
        assert result.passed is False
        assert result.details is not None


class TestValidationReport:
    def test_empty_report_passes(self):
        report = ValidationReport()
        assert report.passed is True
        assert report.error_count == 0
        assert report.warning_count == 0

    def test_report_with_all_passing(self):
        report = ValidationReport(results=[
            ValidationResult(name="Lint", passed=True, message="OK"),
            ValidationResult(name="Types", passed=True, message="OK"),
        ])
        assert report.passed is True
        assert report.error_count == 0

    def test_report_with_error_fails(self):
        report = ValidationReport(results=[
            ValidationResult(name="Lint", passed=True, message="OK"),
            ValidationResult(name="Types", passed=False, message="Failed"),
        ])
        assert report.passed is False
        assert report.error_count == 1

    def test_report_with_warning_only_passes(self):
        report = ValidationReport(results=[
            ValidationResult(
                name="Deprecation",
                passed=False,
                message="Deprecated API",
                severity=ValidationSeverity.WARNING
            ),
        ])
        assert report.passed is True
        assert report.warning_count == 1
        assert report.error_count == 0


class TestQualityGateValidator:
    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_no_gates_returns_empty_report(self, temp_project):
        validator = QualityGateValidator(temp_project)
        feature = Feature(id="test", name="Test", description="Test")
        report = validator.validate(feature)
        assert report.passed is True
        assert len(report.results) == 0

    def test_lint_command_success(self, temp_project):
        validator = QualityGateValidator(temp_project)
        gates = QualityGates(lint_command="echo 'ok'")
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            quality_gates=gates
        )
        report = validator.validate(feature)
        assert report.passed is True
        assert len(report.results) == 1
        assert report.results[0].name == "Lint"

    def test_lint_command_failure(self, temp_project):
        validator = QualityGateValidator(temp_project)
        gates = QualityGates(lint_command="exit 1")
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            quality_gates=gates
        )
        report = validator.validate(feature)
        assert report.passed is False
        assert report.error_count == 1

    def test_type_check_command(self, temp_project):
        validator = QualityGateValidator(temp_project)
        gates = QualityGates(type_check_command="echo 'types ok'")
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            quality_gates=gates
        )
        report = validator.validate(feature)
        assert report.passed is True
        lint_check = next((r for r in report.results if r.name == "Type Check"), None)
        assert lint_check is not None
        assert lint_check.passed is True

    def test_file_size_check_passes(self, temp_project):
        # Create a small Python file
        (temp_project / "small.py").write_text("x = 1\n" * 10)

        validator = QualityGateValidator(temp_project)
        gates = QualityGates(max_file_lines=100)
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            quality_gates=gates
        )
        report = validator.validate(feature)
        assert report.passed is True

    def test_file_size_check_fails(self, temp_project):
        # Create a large Python file
        (temp_project / "large.py").write_text("x = 1\n" * 500)

        validator = QualityGateValidator(temp_project)
        gates = QualityGates(max_file_lines=100)
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            quality_gates=gates
        )
        report = validator.validate(feature)
        assert report.passed is False
        file_check = next((r for r in report.results if r.name == "File Size Check"), None)
        assert file_check is not None
        assert "large.py" in file_check.details

    def test_file_size_skips_node_modules(self, temp_project):
        # Create a large file in node_modules (should be skipped)
        node_modules = temp_project / "node_modules" / "some-package"
        node_modules.mkdir(parents=True)
        (node_modules / "index.js").write_text("x = 1;\n" * 500)

        validator = QualityGateValidator(temp_project)
        gates = QualityGates(max_file_lines=100)
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            quality_gates=gates
        )
        report = validator.validate(feature)
        assert report.passed is True

    def test_custom_validators(self, temp_project):
        validator = QualityGateValidator(temp_project)
        gates = QualityGates(custom_validators=["echo 'check1'", "echo 'check2'"])
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            quality_gates=gates
        )
        report = validator.validate(feature)
        assert report.passed is True
        assert len(report.results) == 2

    def test_custom_validator_failure(self, temp_project):
        validator = QualityGateValidator(temp_project)
        gates = QualityGates(custom_validators=["exit 1"])
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            quality_gates=gates
        )
        report = validator.validate(feature)
        assert report.passed is False


class TestMergeGates:
    @pytest.fixture
    def temp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_merge_with_no_gates(self, temp_project):
        validator = QualityGateValidator(temp_project)
        result = validator._merge_gates(None, None)
        assert result is None

    def test_merge_with_only_feature_gates(self, temp_project):
        validator = QualityGateValidator(temp_project)
        feature_gates = QualityGates(require_tests=True)
        result = validator._merge_gates(feature_gates, None)
        assert result.require_tests is True

    def test_merge_with_only_default_gates(self, temp_project):
        validator = QualityGateValidator(temp_project)
        default_gates = QualityGates(lint_command="ruff check .")
        result = validator._merge_gates(None, default_gates)
        assert result.lint_command == "ruff check ."

    def test_merge_feature_overrides_default(self, temp_project):
        validator = QualityGateValidator(temp_project)
        feature_gates = QualityGates(lint_command="flake8")
        default_gates = QualityGates(lint_command="ruff check .")
        result = validator._merge_gates(feature_gates, default_gates)
        assert result.lint_command == "flake8"

    def test_merge_combines_values(self, temp_project):
        validator = QualityGateValidator(temp_project)
        feature_gates = QualityGates(lint_command="flake8")
        default_gates = QualityGates(
            type_check_command="mypy",
            max_file_lines=400
        )
        result = validator._merge_gates(feature_gates, default_gates)
        assert result.lint_command == "flake8"  # From feature
        assert result.type_check_command == "mypy"  # From default
        assert result.max_file_lines == 400  # From default
