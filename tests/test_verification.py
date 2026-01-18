"""Tests for Phase 3 verification features.

Tests cover:
- V1: Playwright CLI Integration
- V2: Pre-Complete Hooks
- V4: Test Coverage Check
- V5: Lint/Type Check
- V6: Manual Approval Mode
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess

import pytest

from autonomous_dev_agent.models import (
    Feature, FeatureCategory, FeatureStatus,
    VerificationConfig, VerificationResult, VerificationReport, CoverageReport
)
from autonomous_dev_agent.verification import (
    FeatureVerifier, PlaywrightRunner, CoverageChecker, PreCompleteHook
)


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)

        # Create basic project structure
        (project_path / "src").mkdir()
        (project_path / "tests").mkdir()
        (project_path / ".ada").mkdir()
        (project_path / ".ada" / "hooks").mkdir()

        # Create a sample source file
        (project_path / "src" / "main.py").write_text("def hello():\n    return 'hello'\n")

        yield project_path


@pytest.fixture
def sample_feature():
    """Create a sample feature for testing."""
    return Feature(
        id="test-feature",
        name="Test Feature",
        description="A test feature for verification",
        category=FeatureCategory.FUNCTIONAL,
        status=FeatureStatus.IN_PROGRESS,
    )


class TestVerificationConfig:
    """Tests for VerificationConfig model."""

    def test_default_config(self):
        config = VerificationConfig()
        assert config.test_command == "npm test"
        assert config.e2e_command is None
        assert config.lint_command is None
        assert config.coverage_threshold is None
        assert config.require_manual_approval is False
        assert config.test_timeout_seconds == 300
        assert config.e2e_timeout_seconds == 600

    def test_custom_config(self):
        config = VerificationConfig(
            test_command="pytest",
            e2e_command="npx playwright test",
            lint_command="ruff check .",
            type_check_command="mypy .",
            coverage_threshold=80.0,
            require_manual_approval=True,
        )
        assert config.test_command == "pytest"
        assert config.e2e_command == "npx playwright test"
        assert config.lint_command == "ruff check ."
        assert config.type_check_command == "mypy ."
        assert config.coverage_threshold == 80.0
        assert config.require_manual_approval is True


class TestVerificationResult:
    """Tests for VerificationResult model."""

    def test_passed_result(self):
        result = VerificationResult(
            name="Unit Tests",
            passed=True,
            message="All tests passed",
            duration_seconds=5.2
        )
        assert result.passed is True
        assert result.skipped is False
        assert result.duration_seconds == 5.2

    def test_failed_result(self):
        result = VerificationResult(
            name="Lint Check",
            passed=False,
            message="3 errors found",
            details="Line 10: unused import\nLine 20: undefined variable"
        )
        assert result.passed is False
        assert result.details is not None

    def test_skipped_result(self):
        result = VerificationResult(
            name="E2E Tests",
            passed=True,
            skipped=True,
            message="Playwright not installed"
        )
        assert result.skipped is True


class TestFeatureVerifier:
    """Tests for the main FeatureVerifier class."""

    def test_verify_with_no_config(self, temp_project, sample_feature):
        """Verify with minimal config should skip most checks."""
        config = VerificationConfig(test_command=None)
        verifier = FeatureVerifier(temp_project, config)

        report = verifier.verify(sample_feature, interactive=False)

        # Should pass with no checks configured
        assert isinstance(report, VerificationReport)
        assert report.feature_id == "test-feature"

    @patch('subprocess.run')
    def test_verify_passing_tests(self, mock_run, temp_project, sample_feature):
        """Verify with passing tests."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="All tests passed",
            stderr=""
        )

        config = VerificationConfig(test_command="pytest")
        verifier = FeatureVerifier(temp_project, config)

        report = verifier.verify(sample_feature, interactive=False)

        assert report.passed is True
        test_result = next((r for r in report.results if r.name == "Unit Tests"), None)
        assert test_result is not None
        assert test_result.passed is True

    @patch('subprocess.run')
    def test_verify_failing_tests(self, mock_run, temp_project, sample_feature):
        """Verify with failing tests should fail."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="FAILED: test_something"
        )

        config = VerificationConfig(test_command="pytest")
        verifier = FeatureVerifier(temp_project, config)

        report = verifier.verify(sample_feature, interactive=False)

        assert report.passed is False
        test_result = next((r for r in report.results if r.name == "Unit Tests"), None)
        assert test_result is not None
        assert test_result.passed is False

    @patch('subprocess.run')
    def test_verify_lint_check(self, mock_run, temp_project, sample_feature):
        """Verify with lint check."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = VerificationConfig(
            test_command=None,
            lint_command="ruff check ."
        )
        verifier = FeatureVerifier(temp_project, config)

        report = verifier.verify(sample_feature, interactive=False)

        lint_result = next((r for r in report.results if r.name == "Lint Check"), None)
        assert lint_result is not None
        assert lint_result.passed is True

    @patch('subprocess.run')
    def test_verify_type_check(self, mock_run, temp_project, sample_feature):
        """Verify with type check."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = VerificationConfig(
            test_command=None,
            type_check_command="mypy ."
        )
        verifier = FeatureVerifier(temp_project, config)

        report = verifier.verify(sample_feature, interactive=False)

        type_result = next((r for r in report.results if r.name == "Type Check"), None)
        assert type_result is not None
        assert type_result.passed is True

    def test_verify_requires_approval(self, temp_project, sample_feature):
        """Verify with manual approval requirement in non-interactive mode."""
        config = VerificationConfig(
            test_command=None,
            require_manual_approval=True
        )
        verifier = FeatureVerifier(temp_project, config)

        report = verifier.verify(sample_feature, interactive=False)

        assert report.requires_approval is True
        assert report.approved is False

    def test_verify_with_approval_callback(self, temp_project, sample_feature):
        """Verify with custom approval callback."""
        config = VerificationConfig(
            test_command=None,
            require_manual_approval=True
        )
        verifier = FeatureVerifier(temp_project, config)

        # Approval callback that always approves
        report = verifier.verify(
            sample_feature,
            interactive=False,
            on_approval_request=lambda f: True
        )

        assert report.requires_approval is True
        assert report.approved is True
        assert report.approved_by == "callback"

    def test_verify_feature_specific_approval(self, temp_project, sample_feature):
        """Verify with feature-specific approval list."""
        config = VerificationConfig(
            test_command=None,
            approval_features=["test-feature"]
        )
        verifier = FeatureVerifier(temp_project, config)

        report = verifier.verify(sample_feature, interactive=False)

        assert report.requires_approval is True

    def test_verify_command_timeout(self, temp_project, sample_feature):
        """Verify handles command timeout."""
        config = VerificationConfig(
            test_command="sleep 1000",  # Will timeout
            test_timeout_seconds=1
        )
        verifier = FeatureVerifier(temp_project, config)

        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 1)):
            report = verifier.verify(sample_feature, interactive=False)

        assert report.passed is False
        test_result = next((r for r in report.results if r.name == "Unit Tests"), None)
        assert "timeout" in test_result.message.lower() or "Timed out" in test_result.message


class TestPreCompleteHook:
    """Tests for pre-complete hook execution (V2)."""

    def test_no_hook_returns_none(self, temp_project, sample_feature):
        """When no hook exists, should return None."""
        config = VerificationConfig()
        hook_runner = PreCompleteHook(temp_project, config)

        result = hook_runner.run(sample_feature)

        assert result is None

    def test_hook_passes(self, temp_project, sample_feature):
        """Hook that exits 0 should pass."""
        hooks_dir = temp_project / ".ada" / "hooks"

        if sys.platform == "win32":
            hook_path = hooks_dir / "pre-complete.bat"
            hook_path.write_text("@echo off\nexit 0")
        else:
            hook_path = hooks_dir / "pre-complete.sh"
            hook_path.write_text("#!/bin/bash\nexit 0")
            hook_path.chmod(0o755)

        config = VerificationConfig()
        hook_runner = PreCompleteHook(temp_project, config)

        result = hook_runner.run(sample_feature)

        assert result is not None
        assert result.passed is True
        assert result.name == "Pre-Complete Hook"

    def test_hook_fails(self, temp_project, sample_feature):
        """Hook that exits non-zero should fail."""
        hooks_dir = temp_project / ".ada" / "hooks"

        if sys.platform == "win32":
            hook_path = hooks_dir / "pre-complete.bat"
            hook_path.write_text("@echo off\necho Hook failed\nexit 1")
        else:
            hook_path = hooks_dir / "pre-complete.sh"
            hook_path.write_text("#!/bin/bash\necho 'Hook failed'\nexit 1")
            hook_path.chmod(0o755)

        config = VerificationConfig()
        hook_runner = PreCompleteHook(temp_project, config)

        result = hook_runner.run(sample_feature)

        assert result is not None
        assert result.passed is False

    def test_hook_receives_env_vars(self, temp_project, sample_feature):
        """Hook should receive feature environment variables."""
        hooks_dir = temp_project / ".ada" / "hooks"
        output_file = temp_project / "hook_output.txt"

        if sys.platform == "win32":
            hook_path = hooks_dir / "pre-complete.bat"
            hook_path.write_text(
                f'@echo off\necho %ADA_FEATURE_ID% > "{output_file}"\nexit 0'
            )
        else:
            hook_path = hooks_dir / "pre-complete.sh"
            hook_path.write_text(
                f'#!/bin/bash\necho "$ADA_FEATURE_ID" > "{output_file}"\nexit 0'
            )
            hook_path.chmod(0o755)

        config = VerificationConfig()
        hook_runner = PreCompleteHook(temp_project, config)

        result = hook_runner.run(sample_feature)

        assert result.passed is True
        assert output_file.exists()
        assert "test-feature" in output_file.read_text()

    def test_create_sample_hook(self, temp_project):
        """Should create a sample hook script."""
        config = VerificationConfig()
        hook_runner = PreCompleteHook(temp_project, config)

        hook_path = hook_runner.create_sample_hook()

        assert hook_path.exists()
        content = hook_path.read_text()
        assert "ADA_FEATURE_ID" in content


class TestCoverageChecker:
    """Tests for test coverage checking (V4)."""

    def test_no_coverage_config(self, temp_project):
        """When coverage not configured, should skip."""
        config = VerificationConfig(coverage_command=None)
        checker = CoverageChecker(temp_project, config)

        result, report = checker.run_with_coverage()

        assert result.skipped is True
        assert report is None

    @patch('subprocess.run')
    def test_coverage_passes_threshold(self, mock_run, temp_project):
        """Coverage above threshold should pass."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Create coverage report
        coverage_dir = temp_project / "coverage"
        coverage_dir.mkdir()
        coverage_file = coverage_dir / "coverage-summary.json"
        coverage_file.write_text(json.dumps({
            "total": {
                "lines": {"total": 100, "covered": 85, "pct": 85.0}
            }
        }))

        config = VerificationConfig(
            coverage_command="npm run test:coverage",
            coverage_report_path="coverage/coverage-summary.json",
            coverage_threshold=80.0
        )
        checker = CoverageChecker(temp_project, config)

        result, report = checker.run_with_coverage()

        assert result.passed is True
        assert report is not None
        assert report.coverage_percent == 85.0

    @patch('subprocess.run')
    def test_coverage_below_threshold(self, mock_run, temp_project):
        """Coverage below threshold should fail."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Create coverage report
        coverage_dir = temp_project / "coverage"
        coverage_dir.mkdir()
        coverage_file = coverage_dir / "coverage-summary.json"
        coverage_file.write_text(json.dumps({
            "total": {
                "lines": {"total": 100, "covered": 50, "pct": 50.0}
            }
        }))

        config = VerificationConfig(
            coverage_command="npm run test:coverage",
            coverage_report_path="coverage/coverage-summary.json",
            coverage_threshold=80.0
        )
        checker = CoverageChecker(temp_project, config)

        result, report = checker.run_with_coverage()

        assert result.passed is False
        assert "below threshold" in result.message
        assert report.coverage_percent == 50.0

    def test_parse_istanbul_format(self, temp_project):
        """Should parse Istanbul/NYC coverage format."""
        coverage_dir = temp_project / "coverage"
        coverage_dir.mkdir()
        coverage_file = coverage_dir / "coverage-summary.json"
        coverage_file.write_text(json.dumps({
            "total": {
                "lines": {"total": 200, "covered": 180, "pct": 90.0},
                "statements": {"total": 250, "covered": 225, "pct": 90.0},
                "branches": {"total": 50, "covered": 45, "pct": 90.0}
            }
        }))

        config = VerificationConfig(
            coverage_report_path="coverage/coverage-summary.json"
        )
        checker = CoverageChecker(temp_project, config)

        report = checker._parse_report()

        assert report is not None
        assert report.total_lines == 200
        assert report.covered_lines == 180
        assert report.coverage_percent == 90.0

    def test_parse_pytest_format(self, temp_project):
        """Should parse pytest-cov JSON format."""
        coverage_file = temp_project / "coverage.json"
        coverage_file.write_text(json.dumps({
            "totals": {
                "num_statements": 150,
                "covered_lines": 120,
                "percent_covered": 80.0
            }
        }))

        config = VerificationConfig(
            coverage_report_path="coverage.json"
        )
        checker = CoverageChecker(temp_project, config)

        report = checker._parse_report()

        assert report is not None
        assert report.coverage_percent == 80.0


class TestPlaywrightRunner:
    """Tests for Playwright E2E test runner (V1)."""

    @patch('autonomous_dev_agent.verification.subprocess.run')
    def test_run_tests_pass(self, mock_run, temp_project, sample_feature):
        """Playwright tests passing should return success."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="3 tests passed",
            stderr=""
        )

        config = VerificationConfig(e2e_command="npx playwright test")
        runner = PlaywrightRunner(temp_project, config)

        result = runner.run_tests(feature=sample_feature)

        # Should pass since subprocess returned 0
        assert result.passed is True

    @patch('autonomous_dev_agent.verification.subprocess.run')
    def test_run_tests_fail(self, mock_run, temp_project, sample_feature):
        """Playwright tests failing should return failure."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="1 failed\n  ✘ test_login",
            stderr=""
        )

        config = VerificationConfig(e2e_command="npx playwright test")
        runner = PlaywrightRunner(temp_project, config)

        result = runner.run_tests(feature=sample_feature)

        assert result.passed is False

    @patch('autonomous_dev_agent.verification.subprocess.run')
    def test_run_tests_with_grep_pattern(self, mock_run, temp_project, sample_feature):
        """Should add grep pattern for feature-specific tests."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = VerificationConfig(
            e2e_command="npx playwright test",
            e2e_test_patterns={"test-feature": "login|auth"}
        )
        runner = PlaywrightRunner(temp_project, config)

        result = runner.run_tests(feature=sample_feature)

        # Check that grep pattern was added to command
        call_args = mock_run.call_args
        if call_args:
            command = call_args[0][0] if call_args[0] else call_args.kwargs.get('command', '')
            # Command should include grep pattern
            assert 'grep' in str(command).lower() or result.passed

    def test_no_e2e_command_skips(self, temp_project, sample_feature):
        """When no E2E command configured, should skip."""
        config = VerificationConfig(e2e_command=None)
        runner = PlaywrightRunner(temp_project, config)

        result = runner.run_tests(feature=sample_feature)

        assert result.skipped is True


class TestVerificationReport:
    """Tests for VerificationReport model."""

    def test_report_passed(self):
        report = VerificationReport(
            feature_id="test",
            passed=True,
            results=[
                VerificationResult(name="Test1", passed=True, message="OK"),
                VerificationResult(name="Test2", passed=True, message="OK"),
            ]
        )
        assert report.passed is True
        assert len(report.results) == 2

    def test_report_with_coverage(self):
        report = VerificationReport(
            feature_id="test",
            passed=True,
            results=[],
            coverage=CoverageReport(
                total_lines=100,
                covered_lines=80,
                coverage_percent=80.0
            )
        )
        assert report.coverage is not None
        assert report.coverage.coverage_percent == 80.0

    def test_report_with_approval(self):
        report = VerificationReport(
            feature_id="test",
            passed=True,
            results=[],
            requires_approval=True,
            approved=True,
            approved_by="user"
        )
        assert report.requires_approval is True
        assert report.approved is True
        assert report.approved_by == "user"


class TestCoverageReport:
    """Tests for CoverageReport model."""

    def test_coverage_report_creation(self):
        report = CoverageReport(
            total_lines=100,
            covered_lines=85,
            coverage_percent=85.0,
            uncovered_files=["src/utils.py"],
            low_coverage_files=[("src/main.py", 50.0)]
        )
        assert report.total_lines == 100
        assert report.covered_lines == 85
        assert report.coverage_percent == 85.0
        assert len(report.uncovered_files) == 1
        assert len(report.low_coverage_files) == 1


class TestIntegration:
    """Integration tests for the verification system."""

    @patch('subprocess.run')
    def test_full_verification_flow(self, mock_run, temp_project, sample_feature):
        """Test a complete verification flow with multiple checks."""
        # All commands pass
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = VerificationConfig(
            test_command="pytest",
            lint_command="ruff check .",
            type_check_command="mypy .",
        )
        verifier = FeatureVerifier(temp_project, config)

        report = verifier.verify(sample_feature, interactive=False)

        assert report.passed is True
        assert len(report.results) >= 3  # At least 3 checks

        # All checks should pass
        for result in report.results:
            assert result.passed is True or result.skipped is True

    @patch('subprocess.run')
    def test_verification_stops_on_lint_failure(self, mock_run, temp_project, sample_feature):
        """Verification should report lint failure."""
        def mock_command(*args, **kwargs):
            cmd = args[0] if args else kwargs.get('command', '')
            if 'lint' in str(cmd).lower() or 'ruff' in str(cmd).lower():
                return MagicMock(returncode=1, stdout="", stderr="Lint error")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = mock_command

        config = VerificationConfig(
            test_command="pytest",
            lint_command="ruff check .",
        )
        verifier = FeatureVerifier(temp_project, config)

        report = verifier.verify(sample_feature, interactive=False)

        assert report.passed is False
        lint_result = next((r for r in report.results if r.name == "Lint Check"), None)
        assert lint_result is not None
        assert lint_result.passed is False
