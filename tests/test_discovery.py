"""Tests for the discovery module."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from autonomous_dev_agent.models import (
    Backlog,
    BestPracticeViolation,
    CodeIssue,
    DiscoveryResult,
    DiscoveryState,
    IssueCategory,
    ProjectSummary,
    Severity,
    TestGap,
)
from autonomous_dev_agent.discovery.analyzer import CodebaseAnalyzer
from autonomous_dev_agent.discovery.best_practices import BestPracticesChecker
from autonomous_dev_agent.discovery.test_analyzer import TestGapAnalyzer
from autonomous_dev_agent.discovery.tracker import DiscoveryTracker
from autonomous_dev_agent.discovery.backlog_generator import BacklogGenerator


class TestDiscoveryModels:
    """Tests for discovery data models."""

    def test_severity_enum(self):
        """Test Severity enum values."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"

    def test_issue_category_enum(self):
        """Test IssueCategory enum values."""
        assert IssueCategory.BUG.value == "bug"
        assert IssueCategory.SECURITY.value == "security"
        assert IssueCategory.PERFORMANCE.value == "performance"

    def test_code_issue_creation(self):
        """Test CodeIssue model creation."""
        issue = CodeIssue(
            id="test-issue-1",
            file="src/main.py",
            line=42,
            severity=Severity.HIGH,
            category=IssueCategory.BUG,
            title="Null pointer dereference",
            description="Variable may be None before access.",
            suggested_fix="Add null check before accessing.",
        )

        assert issue.id == "test-issue-1"
        assert issue.file == "src/main.py"
        assert issue.line == 42
        assert issue.severity == Severity.HIGH
        assert issue.category == IssueCategory.BUG

    def test_test_gap_creation(self):
        """Test TestGap model creation."""
        gap = TestGap(
            id="test-gap-1",
            module="src/auth.py",
            gap_type="no_tests",
            severity=Severity.HIGH,
            is_critical_path=True,
            description="No tests for authentication module.",
        )

        assert gap.id == "test-gap-1"
        assert gap.module == "src/auth.py"
        assert gap.gap_type == "no_tests"
        assert gap.is_critical_path is True

    def test_best_practice_violation_creation(self):
        """Test BestPracticeViolation model creation."""
        violation = BestPracticeViolation(
            id="bp-1",
            category="linting",
            severity=Severity.MEDIUM,
            title="No linter configured",
            description="No linter configuration found.",
            recommendation="Install and configure ruff.",
        )

        assert violation.id == "bp-1"
        assert violation.category == "linting"

    def test_project_summary_creation(self):
        """Test ProjectSummary model creation."""
        summary = ProjectSummary(
            languages=["python", "javascript"],
            frameworks=["fastapi", "react"],
            structure={"src": "Source code", "tests": "Test files"},
            entry_points=["src/main.py"],
            dependencies={"pydantic": ">=2.0.0"},
            line_counts={"code": 1000, "tests": 500, "docs": 100},
        )

        assert "python" in summary.languages
        assert "fastapi" in summary.frameworks
        assert summary.line_counts["code"] == 1000

    def test_discovery_result_total_issues(self):
        """Test DiscoveryResult.total_issues method."""
        result = DiscoveryResult(
            project_path="/test",
            code_issues=[
                CodeIssue(id="1", file="a.py", title="Issue 1", description="desc"),
                CodeIssue(id="2", file="b.py", title="Issue 2", description="desc"),
            ],
            test_gaps=[
                TestGap(id="3", module="c.py"),
            ],
            best_practice_violations=[
                BestPracticeViolation(
                    id="4", category="test", title="T", description="D", recommendation="R"
                ),
            ],
        )

        assert result.total_issues() == 4

    def test_discovery_result_issues_by_severity(self):
        """Test DiscoveryResult.issues_by_severity method."""
        result = DiscoveryResult(
            project_path="/test",
            code_issues=[
                CodeIssue(id="1", file="a.py", title="I", description="d", severity=Severity.HIGH),
                CodeIssue(id="2", file="b.py", title="I", description="d", severity=Severity.HIGH),
                CodeIssue(id="3", file="c.py", title="I", description="d", severity=Severity.LOW),
            ],
            test_gaps=[
                TestGap(id="4", module="d.py", severity=Severity.MEDIUM),
            ],
        )

        counts = result.issues_by_severity()
        assert counts[Severity.HIGH] == 2
        assert counts[Severity.MEDIUM] == 1
        assert counts[Severity.LOW] == 1
        assert counts[Severity.CRITICAL] == 0

    def test_discovery_state_mark_known(self):
        """Test DiscoveryState.mark_known method."""
        state = DiscoveryState(project_path="/test")
        assert not state.is_known("issue-1")

        state.mark_known("issue-1")
        assert state.is_known("issue-1")

        # Should not duplicate
        state.mark_known("issue-1")
        assert state.known_issue_ids.count("issue-1") == 1

    def test_discovery_state_mark_resolved(self):
        """Test DiscoveryState.mark_resolved method."""
        state = DiscoveryState(project_path="/test")
        assert not state.is_resolved("issue-1")

        state.mark_resolved("issue-1")
        assert state.is_resolved("issue-1")


class TestCodebaseAnalyzer:
    """Tests for CodebaseAnalyzer."""

    def test_analyze_python_project(self, tmp_path: Path):
        """Test analyzing a Python project."""
        # Create a minimal Python project
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test"
version = "0.1.0"
dependencies = ["pydantic>=2.0.0"]
""")

        analyzer = CodebaseAnalyzer(tmp_path)
        summary = analyzer.analyze()

        assert "python" in summary.languages
        assert summary.line_counts["code"] > 0

    def test_detect_frameworks(self, tmp_path: Path):
        """Test framework detection."""
        # Create a file with framework imports
        (tmp_path / "app.py").write_text("""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
""")

        analyzer = CodebaseAnalyzer(tmp_path)
        frameworks = analyzer.detect_frameworks()

        assert "fastapi" in frameworks
        assert "pydantic" in frameworks

    def test_find_entry_points(self, tmp_path: Path):
        """Test finding entry points."""
        (tmp_path / "main.py").write_text("def main(): pass")
        (tmp_path / "cli.py").write_text("import click")
        (tmp_path / "utils.py").write_text("def helper(): pass")

        analyzer = CodebaseAnalyzer(tmp_path)
        entry_points = analyzer.find_entry_points()

        assert "main.py" in entry_points
        assert "cli.py" in entry_points
        # utils.py is not an entry point
        assert "utils.py" not in entry_points


class TestBestPracticesChecker:
    """Tests for BestPracticesChecker."""

    def test_check_missing_gitignore(self, tmp_path: Path):
        """Test detection of missing .gitignore."""
        # Create a git repo without .gitignore
        (tmp_path / ".git").mkdir()

        checker = BestPracticesChecker(tmp_path)
        violations = checker.check_git()

        assert any(v.title == "No .gitignore file" for v in violations)

    def test_check_missing_readme(self, tmp_path: Path):
        """Test detection of missing README."""
        checker = BestPracticesChecker(tmp_path)
        violations = checker.check_documentation()

        assert any(v.title == "No README file" for v in violations)

    def test_no_violation_with_readme(self, tmp_path: Path):
        """Test no README violation when README exists."""
        (tmp_path / "README.md").write_text("# Test Project")

        checker = BestPracticesChecker(tmp_path)
        violations = checker.check_documentation()

        assert not any(v.title == "No README file" for v in violations)

    def test_check_missing_license(self, tmp_path: Path):
        """Test detection of missing LICENSE."""
        checker = BestPracticesChecker(tmp_path)
        violations = checker.check_license()

        assert any(v.title == "No LICENSE file" for v in violations)


class TestTestGapAnalyzer:
    """Tests for TestGapAnalyzer."""

    def test_detect_missing_tests(self, tmp_path: Path):
        """Test detection of modules without tests."""
        # Create source files
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("def login(): pass")
        (tmp_path / "src" / "utils.py").write_text("def helper(): pass")

        analyzer = TestGapAnalyzer(tmp_path, languages=["python"])
        gaps = analyzer.analyze()

        # Should find gaps for both files
        modules = [g.module for g in gaps]
        assert any("auth.py" in m for m in modules)
        assert any("utils.py" in m for m in modules)

    def test_no_gap_when_test_exists(self, tmp_path: Path):
        """Test no gap reported when test file exists."""
        # Create source and test files
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("def login(): pass")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_auth.py").write_text("def test_login(): pass")

        analyzer = TestGapAnalyzer(tmp_path, languages=["python"])
        gaps = analyzer.analyze()

        # auth.py should not have a gap
        assert not any("auth.py" in g.module for g in gaps)

    def test_critical_path_detection(self, tmp_path: Path):
        """Test that critical path files are flagged."""
        (tmp_path / "authentication.py").write_text("def login(): pass")
        (tmp_path / "payment.py").write_text("def charge(): pass")

        analyzer = TestGapAnalyzer(tmp_path, languages=["python"])
        gaps = analyzer.analyze()

        # Both should be marked as critical path
        auth_gap = next((g for g in gaps if "authentication.py" in g.module), None)
        payment_gap = next((g for g in gaps if "payment.py" in g.module), None)

        assert auth_gap is not None and auth_gap.is_critical_path
        assert payment_gap is not None and payment_gap.is_critical_path


class TestDiscoveryTracker:
    """Tests for DiscoveryTracker."""

    def test_save_and_load_state(self, tmp_path: Path):
        """Test saving and loading discovery state."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.state.mark_known("issue-1")
        tracker.state.mark_known("issue-2")
        tracker.state.mark_resolved("issue-1")
        tracker.save_state()

        # Create new tracker and load
        tracker2 = DiscoveryTracker(tmp_path)
        loaded_state = tracker2.load_state()

        assert loaded_state.is_known("issue-1")
        assert loaded_state.is_known("issue-2")
        assert loaded_state.is_resolved("issue-1")

    def test_filter_new_issues(self, tmp_path: Path):
        """Test filtering to only new issues."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.state.mark_known("old-issue")

        result = DiscoveryResult(
            project_path=str(tmp_path),
            code_issues=[
                CodeIssue(id="old-issue", file="a.py", title="Old", description="d"),
                CodeIssue(id="new-issue", file="b.py", title="New", description="d"),
            ],
        )

        filtered = tracker.filter_new_issues(result)

        assert len(filtered.code_issues) == 1
        assert filtered.code_issues[0].id == "new-issue"

    def test_find_resolved_issues(self, tmp_path: Path):
        """Test finding issues that no longer appear."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.state.mark_known("issue-1")
        tracker.state.mark_known("issue-2")

        # Only issue-1 is still present
        result = DiscoveryResult(
            project_path=str(tmp_path),
            code_issues=[
                CodeIssue(id="issue-1", file="a.py", title="I", description="d"),
            ],
        )

        resolved = tracker.find_resolved_issues(result)

        assert "issue-2" in resolved
        assert "issue-1" not in resolved


class TestBacklogGenerator:
    """Tests for BacklogGenerator."""

    def test_generate_from_code_issues(self, tmp_path: Path):
        """Test generating backlog from code issues."""
        result = DiscoveryResult(
            project_path=str(tmp_path),
            code_issues=[
                CodeIssue(
                    id="issue-1",
                    file="auth.py",
                    line=42,
                    severity=Severity.HIGH,
                    category=IssueCategory.SECURITY,
                    title="SQL injection vulnerability",
                    description="User input not sanitized.",
                    suggested_fix="Use parameterized queries.",
                ),
            ],
        )

        generator = BacklogGenerator(tmp_path, project_name="Test")
        backlog = generator.generate(result)

        assert len(backlog.features) == 1
        feature = backlog.features[0]
        assert "SQL injection" in feature.name
        assert feature.priority > 0

    def test_generate_from_test_gaps(self, tmp_path: Path):
        """Test generating backlog from test gaps."""
        result = DiscoveryResult(
            project_path=str(tmp_path),
            test_gaps=[
                TestGap(
                    id="gap-1",
                    module="src/auth.py",
                    gap_type="no_tests",
                    severity=Severity.HIGH,
                    is_critical_path=True,
                ),
            ],
        )

        generator = BacklogGenerator(tmp_path, project_name="Test")
        backlog = generator.generate(result)

        assert len(backlog.features) == 1
        feature = backlog.features[0]
        assert "tests" in feature.name.lower()
        assert "auth.py" in feature.name

    def test_merge_with_existing_backlog(self, tmp_path: Path):
        """Test merging with an existing backlog."""
        # Create existing backlog
        existing = Backlog(
            project_name="Test",
            project_path=str(tmp_path),
            features=[],
        )

        result = DiscoveryResult(
            project_path=str(tmp_path),
            code_issues=[
                CodeIssue(id="new-issue", file="a.py", title="New Issue", description="d"),
            ],
        )

        generator = BacklogGenerator(tmp_path)
        backlog = generator.generate(result, existing_backlog=existing)

        assert len(backlog.features) == 1

    def test_priority_ordering(self, tmp_path: Path):
        """Test that features are ordered by priority."""
        result = DiscoveryResult(
            project_path=str(tmp_path),
            code_issues=[
                CodeIssue(id="low", file="a.py", title="Low", description="d", severity=Severity.LOW),
                CodeIssue(id="critical", file="b.py", title="Critical", description="d", severity=Severity.CRITICAL),
                CodeIssue(id="high", file="c.py", title="High", description="d", severity=Severity.HIGH),
            ],
        )

        generator = BacklogGenerator(tmp_path)
        backlog = generator.generate(result)

        # Features should be ordered by priority (descending)
        priorities = [f.priority for f in backlog.features]
        assert priorities == sorted(priorities, reverse=True)


class TestIntegration:
    """Integration tests for the discovery module."""

    def test_full_discovery_flow(self, tmp_path: Path):
        """Test the full discovery flow on a minimal project."""
        # Create a minimal Python project
        (tmp_path / ".git").mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("""
def main():
    print("Hello")

if __name__ == "__main__":
    main()
""")
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test-project"
version = "0.1.0"
dependencies = []
""")

        # Run analysis
        analyzer = CodebaseAnalyzer(tmp_path)
        summary = analyzer.analyze()

        assert "python" in summary.languages

        # Check best practices
        bp_checker = BestPracticesChecker(tmp_path, languages=summary.languages)
        violations = bp_checker.check_all()

        # Should find at least some violations (no README, no tests, etc.)
        assert len(violations) > 0

        # Check test gaps
        test_analyzer = TestGapAnalyzer(tmp_path, languages=summary.languages)
        gaps = test_analyzer.analyze()

        # Should find gap for main.py
        assert any("main.py" in g.module for g in gaps)

        # Generate backlog
        result = DiscoveryResult(
            project_path=str(tmp_path),
            summary=summary,
            code_issues=[],
            test_gaps=gaps,
            best_practice_violations=violations,
        )

        generator = BacklogGenerator(tmp_path, project_name="Test")
        backlog = generator.generate(result)

        # Should have features from violations and gaps
        assert len(backlog.features) > 0
