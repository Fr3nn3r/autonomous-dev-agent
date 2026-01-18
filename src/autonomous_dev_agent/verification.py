"""Feature verification engine (Phase 3).

Provides comprehensive verification before marking features complete:
- V1: Playwright CLI integration for E2E testing
- V2: Pre-complete hooks for custom validation
- V4: Test coverage checking
- V5: Lint and type check validation
- V6: Manual approval mode
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Callable

from rich.console import Console
from rich.prompt import Confirm

from .models import (
    Feature, VerificationConfig, VerificationResult,
    VerificationReport, CoverageReport
)


console = Console()


class FeatureVerifier:
    """Comprehensive feature verification engine.

    Runs all configured verification checks before allowing a feature
    to be marked as complete.
    """

    def __init__(
        self,
        project_path: Path | str,
        config: Optional[VerificationConfig] = None
    ):
        self.project_path = Path(project_path)
        self.config = config or VerificationConfig()

    def verify(
        self,
        feature: Feature,
        interactive: bool = True,
        on_approval_request: Optional[Callable[[Feature], bool]] = None
    ) -> VerificationReport:
        """Run all verification checks for a feature.

        Args:
            feature: The feature to verify
            interactive: Whether to prompt for manual approval if required
            on_approval_request: Custom callback for approval (returns True if approved)

        Returns:
            VerificationReport with all check results
        """
        results: list[VerificationResult] = []

        # V5: Lint check
        if self.config.lint_command:
            results.append(self._run_lint_check())

        # V5: Type check
        if self.config.type_check_command:
            results.append(self._run_type_check())

        # V1: Unit tests
        if self.config.test_command:
            results.append(self._run_unit_tests())

        # V1: E2E tests (Playwright)
        if self.config.e2e_command:
            results.append(self._run_e2e_tests(feature))

        # V4: Coverage check
        if self.config.coverage_command:
            coverage_result, coverage_report = self._run_coverage_check()
            results.append(coverage_result)
        else:
            coverage_report = None

        # V2: Pre-complete hooks
        hook_result = self._run_pre_complete_hook(feature)
        if hook_result:
            results.append(hook_result)

        # Determine if all checks passed
        all_passed = all(r.passed or r.skipped for r in results)

        # V6: Manual approval
        requires_approval = self._requires_approval(feature)
        approved = False
        approved_by = None

        if requires_approval and all_passed:
            if on_approval_request:
                approved = on_approval_request(feature)
                approved_by = "callback"
            elif interactive:
                approved = self._prompt_for_approval(feature, results)
                approved_by = "user" if approved else None
            else:
                # Non-interactive mode, approval required but not given
                results.append(VerificationResult(
                    name="Manual Approval",
                    passed=False,
                    message="Manual approval required but not available (non-interactive mode)"
                ))

        # Final pass determination
        if requires_approval:
            final_passed = all_passed and approved
        else:
            final_passed = all_passed

        return VerificationReport(
            feature_id=feature.id,
            passed=final_passed,
            results=results,
            coverage=coverage_report,
            requires_approval=requires_approval,
            approved=approved,
            approved_by=approved_by
        )

    def _run_lint_check(self) -> VerificationResult:
        """Run lint check (V5)."""
        return self._run_command(
            name="Lint Check",
            command=self.config.lint_command,
            timeout=self.config.test_timeout_seconds
        )

    def _run_type_check(self) -> VerificationResult:
        """Run type check (V5)."""
        return self._run_command(
            name="Type Check",
            command=self.config.type_check_command,
            timeout=self.config.test_timeout_seconds
        )

    def _run_unit_tests(self) -> VerificationResult:
        """Run unit tests."""
        return self._run_command(
            name="Unit Tests",
            command=self.config.test_command,
            timeout=self.config.test_timeout_seconds
        )

    def _run_e2e_tests(self, feature: Feature) -> VerificationResult:
        """Run E2E tests with Playwright CLI (V1).

        Supports feature-specific test patterns via grep.
        """
        command = self.config.e2e_command

        # Check if Playwright is available
        if not self._is_playwright_available():
            return VerificationResult(
                name="E2E Tests (Playwright)",
                passed=True,
                skipped=True,
                message="Playwright not installed - skipping E2E tests"
            )

        # Add feature-specific grep pattern if configured
        if feature.id in self.config.e2e_test_patterns:
            pattern = self.config.e2e_test_patterns[feature.id]
            command = f"{command} --grep \"{pattern}\""

        return self._run_command(
            name="E2E Tests (Playwright)",
            command=command,
            timeout=self.config.e2e_timeout_seconds
        )

    def _run_coverage_check(self) -> tuple[VerificationResult, Optional[CoverageReport]]:
        """Run tests with coverage and check threshold (V4)."""
        start_time = time.time()

        # Run coverage command
        result = self._run_command(
            name="Coverage",
            command=self.config.coverage_command,
            timeout=self.config.test_timeout_seconds
        )

        if not result.passed:
            return result, None

        # Parse coverage report if path is configured
        coverage_report = None
        if self.config.coverage_report_path:
            coverage_report = self._parse_coverage_report()

            # Check threshold if configured
            if self.config.coverage_threshold and coverage_report:
                if coverage_report.coverage_percent < self.config.coverage_threshold:
                    duration = time.time() - start_time
                    return VerificationResult(
                        name="Coverage Threshold",
                        passed=False,
                        message=f"Coverage {coverage_report.coverage_percent:.1f}% is below threshold {self.config.coverage_threshold}%",
                        duration_seconds=duration,
                        details=self._format_coverage_details(coverage_report)
                    ), coverage_report

        return result, coverage_report

    def _parse_coverage_report(self) -> Optional[CoverageReport]:
        """Parse coverage report from configured path.

        Supports multiple formats:
        - Istanbul/NYC JSON (coverage-summary.json)
        - pytest-cov JSON
        - Generic JSON with 'total' key
        """
        report_path = self.project_path / self.config.coverage_report_path

        if not report_path.exists():
            return None

        try:
            data = json.loads(report_path.read_text())

            # Istanbul/NYC format
            if "total" in data and "lines" in data.get("total", {}):
                total = data["total"]["lines"]
                return CoverageReport(
                    total_lines=total.get("total", 0),
                    covered_lines=total.get("covered", 0),
                    coverage_percent=total.get("pct", 0.0)
                )

            # pytest-cov format
            if "totals" in data:
                totals = data["totals"]
                return CoverageReport(
                    total_lines=totals.get("num_statements", 0),
                    covered_lines=totals.get("covered_lines", 0),
                    coverage_percent=totals.get("percent_covered", 0.0)
                )

            # Generic format with coverage_percent
            if "coverage_percent" in data:
                return CoverageReport(
                    coverage_percent=data.get("coverage_percent", 0.0)
                )

        except (json.JSONDecodeError, KeyError):
            pass

        return None

    def _format_coverage_details(self, report: CoverageReport) -> str:
        """Format coverage report details for display."""
        lines = [f"Total coverage: {report.coverage_percent:.1f}%"]

        if report.uncovered_files:
            lines.append(f"\nFiles with no coverage ({len(report.uncovered_files)}):")
            for f in report.uncovered_files[:5]:
                lines.append(f"  - {f}")
            if len(report.uncovered_files) > 5:
                lines.append(f"  ... and {len(report.uncovered_files) - 5} more")

        if report.low_coverage_files:
            lines.append(f"\nFiles with low coverage ({len(report.low_coverage_files)}):")
            for f, pct in report.low_coverage_files[:5]:
                lines.append(f"  - {f}: {pct:.1f}%")

        return "\n".join(lines)

    def _run_pre_complete_hook(self, feature: Feature) -> Optional[VerificationResult]:
        """Run pre-complete hook script (V2).

        Looks for hook script in:
        1. Config-specified path
        2. .ada/hooks/pre-complete.sh
        3. .ada/hooks/pre-complete.ps1 (Windows)
        """
        hook_path = self._find_hook_script()

        if not hook_path:
            return None  # No hook configured, skip silently

        # Set environment variables for the hook
        env = os.environ.copy()
        env.update({
            "ADA_PROJECT_PATH": str(self.project_path),
            "ADA_FEATURE_ID": feature.id,
            "ADA_FEATURE_NAME": feature.name,
            "ADA_FEATURE_CATEGORY": feature.category.value,
        })

        return self._run_command(
            name="Pre-Complete Hook",
            command=str(hook_path),
            timeout=self.config.test_timeout_seconds,
            env=env,
            shell=True
        )

    def _find_hook_script(self) -> Optional[Path]:
        """Find the pre-complete hook script."""
        # Check config-specified path first
        if self.config.pre_complete_hook:
            hook_path = self.project_path / self.config.pre_complete_hook
            if hook_path.exists():
                return hook_path

        # Check default locations
        hooks_dir = self.project_path / self.config.hooks_dir

        # Platform-appropriate scripts
        if sys.platform == "win32":
            candidates = ["pre-complete.ps1", "pre-complete.bat", "pre-complete.cmd", "pre-complete.sh"]
        else:
            candidates = ["pre-complete.sh", "pre-complete"]

        for name in candidates:
            hook_path = hooks_dir / name
            if hook_path.exists():
                return hook_path

        return None

    def _requires_approval(self, feature: Feature) -> bool:
        """Check if feature requires manual approval (V6)."""
        # Check if feature is in the approval list
        if self.config.approval_features:
            return feature.id in self.config.approval_features

        # Fall back to global setting
        return self.config.require_manual_approval

    def _prompt_for_approval(
        self,
        feature: Feature,
        results: list[VerificationResult]
    ) -> bool:
        """Prompt user for manual approval (V6)."""
        console.print("\n" + "=" * 60)
        console.print(f"[bold yellow]Manual Approval Required[/bold yellow]")
        console.print("=" * 60)

        console.print(f"\n[bold]Feature:[/bold] {feature.name}")
        console.print(f"[bold]ID:[/bold] {feature.id}")
        console.print(f"[bold]Description:[/bold] {feature.description}")

        # Show verification results
        console.print("\n[bold]Verification Results:[/bold]")
        for r in results:
            if r.skipped:
                console.print(f"  [dim]⊘ {r.name}: {r.message}[/dim]")
            elif r.passed:
                console.print(f"  [green]✓ {r.name}[/green]: {r.message}")
            else:
                console.print(f"  [red]✗ {r.name}[/red]: {r.message}")

        console.print("")
        return Confirm.ask("Approve this feature as complete?", default=False)

    def _run_command(
        self,
        name: str,
        command: Optional[str],
        timeout: int,
        env: Optional[dict] = None,
        shell: bool = True
    ) -> VerificationResult:
        """Run a shell command and return result."""
        if not command:
            return VerificationResult(
                name=name,
                passed=True,
                skipped=True,
                message="Not configured"
            )

        start_time = time.time()

        try:
            result = subprocess.run(
                command,
                shell=shell,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env or os.environ
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                return VerificationResult(
                    name=name,
                    passed=True,
                    message="Passed",
                    duration_seconds=duration
                )
            else:
                output = (result.stdout + result.stderr).strip()
                if len(output) > 1000:
                    output = output[:1000] + "\n... (truncated)"

                return VerificationResult(
                    name=name,
                    passed=False,
                    message=f"Failed (exit code {result.returncode})",
                    duration_seconds=duration,
                    details=output
                )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return VerificationResult(
                name=name,
                passed=False,
                message=f"Timed out after {timeout} seconds",
                duration_seconds=duration
            )
        except Exception as e:
            duration = time.time() - start_time
            return VerificationResult(
                name=name,
                passed=False,
                message=f"Error: {e}",
                duration_seconds=duration
            )

    def _is_playwright_available(self) -> bool:
        """Check if Playwright CLI is available."""
        # Check for npx playwright
        npx_path = shutil.which("npx")
        if npx_path:
            # Check if playwright is installed in node_modules
            node_modules = self.project_path / "node_modules" / "playwright"
            if node_modules.exists():
                return True

            # Check global playwright
            try:
                result = subprocess.run(
                    ["npx", "playwright", "--version"],
                    capture_output=True,
                    timeout=10
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        return False


class PlaywrightRunner:
    """Specialized runner for Playwright E2E tests (V1).

    Provides additional features beyond basic command execution:
    - Test filtering by feature
    - Screenshot capture
    - Visual regression support
    - Detailed reporting
    """

    def __init__(
        self,
        project_path: Path | str,
        config: Optional[VerificationConfig] = None
    ):
        self.project_path = Path(project_path)
        self.config = config or VerificationConfig()

    def run_tests(
        self,
        feature: Optional[Feature] = None,
        grep_pattern: Optional[str] = None,
        update_snapshots: bool = False
    ) -> VerificationResult:
        """Run Playwright tests.

        Args:
            feature: Feature to filter tests for
            grep_pattern: Custom grep pattern for test filtering
            update_snapshots: Whether to update visual snapshots

        Returns:
            VerificationResult with test outcome
        """
        if not self.config.e2e_command:
            return VerificationResult(
                name="Playwright E2E",
                passed=True,
                skipped=True,
                message="E2E command not configured"
            )

        # Build command
        cmd_parts = [self.config.e2e_command]

        # Add grep pattern
        if grep_pattern:
            cmd_parts.append(f'--grep "{grep_pattern}"')
        elif feature and feature.id in self.config.e2e_test_patterns:
            pattern = self.config.e2e_test_patterns[feature.id]
            cmd_parts.append(f'--grep "{pattern}"')

        # Update snapshots if requested
        if update_snapshots:
            cmd_parts.append("--update-snapshots")

        command = " ".join(cmd_parts)

        start_time = time.time()

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=self.config.e2e_timeout_seconds
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                return VerificationResult(
                    name="Playwright E2E",
                    passed=True,
                    message="All E2E tests passed",
                    duration_seconds=duration
                )
            else:
                # Parse Playwright output for better error reporting
                output = result.stdout + result.stderr
                failed_tests = self._parse_failed_tests(output)

                details = output if len(output) <= 2000 else output[:2000] + "\n... (truncated)"

                return VerificationResult(
                    name="Playwright E2E",
                    passed=False,
                    message=f"{len(failed_tests)} test(s) failed" if failed_tests else "Tests failed",
                    duration_seconds=duration,
                    details=details
                )

        except subprocess.TimeoutExpired:
            return VerificationResult(
                name="Playwright E2E",
                passed=False,
                message=f"E2E tests timed out after {self.config.e2e_timeout_seconds}s"
            )
        except Exception as e:
            return VerificationResult(
                name="Playwright E2E",
                passed=False,
                message=f"Error running E2E tests: {e}"
            )

    def _parse_failed_tests(self, output: str) -> list[str]:
        """Parse Playwright output to extract failed test names."""
        failed = []
        for line in output.split("\n"):
            # Playwright outputs failed tests with specific patterns
            if "✘" in line or "failed" in line.lower():
                # Extract test name if possible
                if "›" in line:
                    parts = line.split("›")
                    if len(parts) >= 2:
                        failed.append(parts[-1].strip())
        return failed

    def capture_screenshot(
        self,
        url: str,
        output_path: str,
        full_page: bool = True
    ) -> VerificationResult:
        """Capture a screenshot using Playwright.

        Useful for visual regression testing setup.
        """
        script = f"""
const {{ chromium }} = require('playwright');
(async () => {{
    const browser = await chromium.launch();
    const page = await browser.newPage();
    await page.goto('{url}');
    await page.screenshot({{ path: '{output_path}', fullPage: {str(full_page).lower()} }});
    await browser.close();
}})();
"""

        script_path = self.project_path / ".ada" / "temp_screenshot.js"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script)

        try:
            result = subprocess.run(
                ["node", str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.project_path
            )

            if result.returncode == 0:
                return VerificationResult(
                    name="Screenshot Capture",
                    passed=True,
                    message=f"Screenshot saved to {output_path}"
                )
            else:
                return VerificationResult(
                    name="Screenshot Capture",
                    passed=False,
                    message="Failed to capture screenshot",
                    details=result.stderr
                )

        except Exception as e:
            return VerificationResult(
                name="Screenshot Capture",
                passed=False,
                message=f"Error: {e}"
            )
        finally:
            if script_path.exists():
                script_path.unlink()


class CoverageChecker:
    """Test coverage analysis (V4).

    Parses coverage reports from various tools and checks against thresholds.
    """

    def __init__(
        self,
        project_path: Path | str,
        config: Optional[VerificationConfig] = None
    ):
        self.project_path = Path(project_path)
        self.config = config or VerificationConfig()

    def run_with_coverage(self) -> tuple[VerificationResult, Optional[CoverageReport]]:
        """Run tests with coverage collection."""
        if not self.config.coverage_command:
            return VerificationResult(
                name="Coverage",
                passed=True,
                skipped=True,
                message="Coverage command not configured"
            ), None

        start_time = time.time()

        try:
            result = subprocess.run(
                self.config.coverage_command,
                shell=True,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=self.config.test_timeout_seconds
            )

            duration = time.time() - start_time

            if result.returncode != 0:
                return VerificationResult(
                    name="Coverage",
                    passed=False,
                    message="Tests failed during coverage run",
                    duration_seconds=duration,
                    details=result.stderr[:1000] if result.stderr else None
                ), None

            # Parse coverage report
            report = self._parse_report()

            if not report:
                return VerificationResult(
                    name="Coverage",
                    passed=True,
                    message="Tests passed, but coverage report not found",
                    duration_seconds=duration
                ), None

            # Check threshold
            if self.config.coverage_threshold:
                if report.coverage_percent < self.config.coverage_threshold:
                    return VerificationResult(
                        name="Coverage",
                        passed=False,
                        message=f"Coverage {report.coverage_percent:.1f}% below threshold {self.config.coverage_threshold}%",
                        duration_seconds=duration
                    ), report

            return VerificationResult(
                name="Coverage",
                passed=True,
                message=f"Coverage: {report.coverage_percent:.1f}%",
                duration_seconds=duration
            ), report

        except subprocess.TimeoutExpired:
            return VerificationResult(
                name="Coverage",
                passed=False,
                message=f"Coverage run timed out after {self.config.test_timeout_seconds}s"
            ), None
        except Exception as e:
            return VerificationResult(
                name="Coverage",
                passed=False,
                message=f"Error: {e}"
            ), None

    def _parse_report(self) -> Optional[CoverageReport]:
        """Parse coverage report from configured path."""
        if not self.config.coverage_report_path:
            return self._try_common_paths()

        report_path = self.project_path / self.config.coverage_report_path

        if not report_path.exists():
            return None

        return self._parse_json_report(report_path)

    def _try_common_paths(self) -> Optional[CoverageReport]:
        """Try common coverage report locations."""
        common_paths = [
            "coverage/coverage-summary.json",  # Istanbul/NYC
            "coverage.json",  # pytest-cov
            "coverage/lcov-report/index.json",  # LCOV
            ".coverage.json",  # Various tools
        ]

        for path in common_paths:
            report_path = self.project_path / path
            if report_path.exists():
                report = self._parse_json_report(report_path)
                if report:
                    return report

        return None

    def _parse_json_report(self, path: Path) -> Optional[CoverageReport]:
        """Parse a JSON coverage report."""
        try:
            data = json.loads(path.read_text())

            # Istanbul/NYC format
            if "total" in data:
                total = data["total"]
                if "lines" in total:
                    lines = total["lines"]
                    return CoverageReport(
                        total_lines=lines.get("total", 0),
                        covered_lines=lines.get("covered", 0),
                        coverage_percent=lines.get("pct", 0.0)
                    )

            # pytest-cov JSON format
            if "totals" in data:
                totals = data["totals"]
                return CoverageReport(
                    total_lines=totals.get("num_statements", 0),
                    covered_lines=totals.get("covered_lines", 0),
                    coverage_percent=totals.get("percent_covered", 0.0)
                )

            # Simple format
            if "coverage_percent" in data or "coverage" in data:
                return CoverageReport(
                    coverage_percent=data.get("coverage_percent", data.get("coverage", 0.0))
                )

        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        return None

    def get_uncovered_files(self) -> list[str]:
        """Get list of files with no test coverage."""
        report = self._parse_report()
        if report:
            return report.uncovered_files
        return []


class PreCompleteHook:
    """Pre-complete hook execution (V2).

    Allows custom validation scripts to run before feature completion.
    """

    def __init__(
        self,
        project_path: Path | str,
        config: Optional[VerificationConfig] = None
    ):
        self.project_path = Path(project_path)
        self.config = config or VerificationConfig()

    def run(self, feature: Feature) -> Optional[VerificationResult]:
        """Run the pre-complete hook if configured."""
        hook_path = self._find_hook()

        if not hook_path:
            return None

        # Prepare environment
        env = os.environ.copy()
        env.update({
            "ADA_PROJECT_PATH": str(self.project_path),
            "ADA_FEATURE_ID": feature.id,
            "ADA_FEATURE_NAME": feature.name,
            "ADA_FEATURE_DESCRIPTION": feature.description,
            "ADA_FEATURE_CATEGORY": feature.category.value,
            "ADA_FEATURE_PRIORITY": str(feature.priority),
        })

        # Determine how to run the script
        if hook_path.suffix == ".ps1" and sys.platform == "win32":
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(hook_path)]
        elif hook_path.suffix in (".bat", ".cmd"):
            cmd = ["cmd", "/c", str(hook_path)]
        else:
            # Unix shell script or generic
            cmd = str(hook_path)

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                shell=isinstance(cmd, str),
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=self.config.test_timeout_seconds,
                env=env
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                return VerificationResult(
                    name="Pre-Complete Hook",
                    passed=True,
                    message="Hook passed",
                    duration_seconds=duration
                )
            else:
                output = (result.stdout + result.stderr).strip()
                return VerificationResult(
                    name="Pre-Complete Hook",
                    passed=False,
                    message=f"Hook failed (exit code {result.returncode})",
                    duration_seconds=duration,
                    details=output[:1000] if output else None
                )

        except subprocess.TimeoutExpired:
            return VerificationResult(
                name="Pre-Complete Hook",
                passed=False,
                message=f"Hook timed out after {self.config.test_timeout_seconds}s"
            )
        except FileNotFoundError:
            return VerificationResult(
                name="Pre-Complete Hook",
                passed=False,
                message=f"Hook script not found or not executable: {hook_path}"
            )
        except Exception as e:
            return VerificationResult(
                name="Pre-Complete Hook",
                passed=False,
                message=f"Error running hook: {e}"
            )

    def _find_hook(self) -> Optional[Path]:
        """Find the pre-complete hook script."""
        # Check explicit config path
        if self.config.pre_complete_hook:
            hook_path = self.project_path / self.config.pre_complete_hook
            if hook_path.exists():
                return hook_path

        # Check hooks directory
        hooks_dir = self.project_path / self.config.hooks_dir

        if not hooks_dir.exists():
            return None

        # Platform-specific search order
        if sys.platform == "win32":
            candidates = ["pre-complete.ps1", "pre-complete.bat", "pre-complete.cmd", "pre-complete.sh"]
        else:
            candidates = ["pre-complete.sh", "pre-complete"]

        for name in candidates:
            hook_path = hooks_dir / name
            if hook_path.exists():
                return hook_path

        return None

    def create_sample_hook(self) -> Path:
        """Create a sample pre-complete hook script."""
        hooks_dir = self.project_path / self.config.hooks_dir
        hooks_dir.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            hook_path = hooks_dir / "pre-complete.ps1"
            content = '''# ADA Pre-Complete Hook (PowerShell)
# This script runs before a feature is marked complete.
# Exit with non-zero to prevent completion.

param()

Write-Host "Running pre-complete validation..."
Write-Host "Feature: $env:ADA_FEATURE_ID"
Write-Host "Name: $env:ADA_FEATURE_NAME"

# Add your custom validation here
# Example: Check for TODO comments
# $todos = git grep -n "TODO" -- "*.py" "*.ts" "*.js"
# if ($todos) {
#     Write-Host "ERROR: Found TODO comments:"
#     Write-Host $todos
#     exit 1
# }

Write-Host "Pre-complete hook passed!"
exit 0
'''
        else:
            hook_path = hooks_dir / "pre-complete.sh"
            content = '''#!/bin/bash
# ADA Pre-Complete Hook
# This script runs before a feature is marked complete.
# Exit with non-zero to prevent completion.

echo "Running pre-complete validation..."
echo "Feature: $ADA_FEATURE_ID"
echo "Name: $ADA_FEATURE_NAME"

# Add your custom validation here
# Example: Check for TODO comments
# if git grep -q "TODO" -- "*.py" "*.ts" "*.js"; then
#     echo "ERROR: Found TODO comments"
#     git grep -n "TODO" -- "*.py" "*.ts" "*.js"
#     exit 1
# fi

echo "Pre-complete hook passed!"
exit 0
'''

        hook_path.write_text(content)

        # Make executable on Unix
        if sys.platform != "win32":
            hook_path.chmod(0o755)

        return hook_path
