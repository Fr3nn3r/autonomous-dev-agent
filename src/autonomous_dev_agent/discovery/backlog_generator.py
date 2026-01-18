"""Backlog generator from discovery results.

Converts discovered issues into Feature objects for the backlog.
"""

from datetime import datetime
from pathlib import Path

from ..models import (
    Backlog,
    BestPracticeViolation,
    CodeIssue,
    DiscoveryResult,
    Feature,
    FeatureCategory,
    FeatureStatus,
    IssueCategory,
    Severity,
    TestGap,
)
from .requirements import ExtractedRequirement


# Severity to priority mapping
SEVERITY_PRIORITY: dict[Severity, int] = {
    Severity.CRITICAL: 100,
    Severity.HIGH: 75,
    Severity.MEDIUM: 50,
    Severity.LOW: 25,
}

# Issue category to feature category mapping
ISSUE_TO_FEATURE_CATEGORY: dict[IssueCategory, FeatureCategory] = {
    IssueCategory.BUG: FeatureCategory.BUGFIX,
    IssueCategory.SECURITY: FeatureCategory.BUGFIX,  # Security issues are critical bugs
    IssueCategory.PERFORMANCE: FeatureCategory.REFACTOR,
    IssueCategory.CODE_SMELL: FeatureCategory.REFACTOR,
    IssueCategory.ERROR_HANDLING: FeatureCategory.BUGFIX,
    IssueCategory.VALIDATION: FeatureCategory.BUGFIX,
    IssueCategory.HARDCODED: FeatureCategory.REFACTOR,
    IssueCategory.DEPRECATED: FeatureCategory.REFACTOR,
}


class BacklogGenerator:
    """Generates backlog items from discovery results."""

    def __init__(self, project_path: Path | str, project_name: str | None = None):
        """Initialize the generator.

        Args:
            project_path: Path to the project root directory.
            project_name: Name of the project (default: directory name).
        """
        self.project_path = Path(project_path).resolve()
        self.project_name = project_name or self.project_path.name

    def generate(
        self,
        result: DiscoveryResult,
        requirements: list[ExtractedRequirement] | None = None,
        existing_backlog: Backlog | None = None,
    ) -> Backlog:
        """Generate a backlog from discovery results.

        Args:
            result: Discovery result with issues.
            requirements: Optional extracted requirements.
            existing_backlog: Optional existing backlog to merge with.

        Returns:
            Generated or updated Backlog.
        """
        # Start with existing backlog or create new one
        if existing_backlog:
            backlog = existing_backlog
        else:
            backlog = Backlog(
                project_name=self.project_name,
                project_path=str(self.project_path),
                features=[],
            )

        # Track existing feature IDs to avoid duplicates
        existing_ids = {f.id for f in backlog.features}

        # Convert code issues to features
        for issue in result.code_issues:
            feature = self._issue_to_feature(issue)
            if feature.id not in existing_ids:
                backlog.features.append(feature)
                existing_ids.add(feature.id)

        # Convert test gaps to features
        for gap in result.test_gaps:
            feature = self._test_gap_to_feature(gap)
            if feature.id not in existing_ids:
                backlog.features.append(feature)
                existing_ids.add(feature.id)

        # Convert best practice violations to features
        for violation in result.best_practice_violations:
            feature = self._violation_to_feature(violation)
            if feature.id not in existing_ids:
                backlog.features.append(feature)
                existing_ids.add(feature.id)

        # Convert requirements to features
        if requirements:
            for req in requirements:
                if req.status in ("not_implemented", "partial"):
                    feature = self._requirement_to_feature(req)
                    if feature.id not in existing_ids:
                        backlog.features.append(feature)
                        existing_ids.add(feature.id)

        # Sort features by priority (descending)
        backlog.features.sort(key=lambda f: f.priority, reverse=True)

        # Update timestamp
        backlog.last_updated = datetime.now()

        return backlog

    def _issue_to_feature(self, issue: CodeIssue) -> Feature:
        """Convert a code issue to a feature.

        Args:
            issue: Code issue to convert.

        Returns:
            Feature object.
        """
        # Determine category
        category = ISSUE_TO_FEATURE_CATEGORY.get(
            issue.category,
            FeatureCategory.BUGFIX,
        )

        # Determine priority
        priority = SEVERITY_PRIORITY.get(issue.severity, 50)

        # Boost priority for security issues
        if issue.category == IssueCategory.SECURITY:
            priority += 25

        # Build description
        description = issue.description
        if issue.suggested_fix:
            description += f"\n\nSuggested fix: {issue.suggested_fix}"

        # Build acceptance criteria
        criteria = [
            f"Issue in {issue.file} is resolved",
        ]
        if issue.line:
            criteria.append(f"Line {issue.line} no longer has the issue")
        if issue.category == IssueCategory.SECURITY:
            criteria.append("Security vulnerability is verified as fixed")
        if issue.category == IssueCategory.BUG:
            criteria.append("Add test case to prevent regression")

        return Feature(
            id=f"discovery-{issue.id}",
            name=f"Fix: {issue.title}",
            description=description,
            category=category,
            status=FeatureStatus.PENDING,
            priority=priority,
            acceptance_criteria=criteria,
        )

    def _test_gap_to_feature(self, gap: TestGap) -> Feature:
        """Convert a test gap to a feature.

        Args:
            gap: Test gap to convert.

        Returns:
            Feature object.
        """
        # Determine priority
        priority = SEVERITY_PRIORITY.get(gap.severity, 50)

        # Boost priority for critical paths
        if gap.is_critical_path:
            priority += 20

        # Build description based on gap type
        if gap.gap_type == "no_tests":
            description = f"Add comprehensive tests for {gap.module}."
        elif gap.gap_type == "partial_coverage":
            description = f"Improve test coverage for {gap.module}."
        else:  # missing_edge_cases
            description = f"Add edge case tests for {gap.module}."

        if gap.description:
            description += f"\n\n{gap.description}"

        # Build acceptance criteria
        criteria = [
            f"Tests exist for {gap.module}",
            "Tests cover happy path scenarios",
            "Tests cover error handling",
        ]
        if gap.is_critical_path:
            criteria.append("Critical path has comprehensive coverage")

        return Feature(
            id=f"discovery-{gap.id}",
            name=f"Add tests: {gap.module}",
            description=description,
            category=FeatureCategory.TESTING,
            status=FeatureStatus.PENDING,
            priority=priority,
            acceptance_criteria=criteria,
        )

    def _violation_to_feature(self, violation: BestPracticeViolation) -> Feature:
        """Convert a best practice violation to a feature.

        Args:
            violation: Violation to convert.

        Returns:
            Feature object.
        """
        # Determine priority
        priority = SEVERITY_PRIORITY.get(violation.severity, 25)

        # Build description
        description = violation.description
        description += f"\n\nRecommendation: {violation.recommendation}"

        # Build acceptance criteria
        criteria = [
            f"{violation.category.title()} best practice is followed",
            violation.recommendation,
        ]

        return Feature(
            id=f"discovery-{violation.id}",
            name=violation.title,
            description=description,
            category=FeatureCategory.INFRASTRUCTURE,
            status=FeatureStatus.PENDING,
            priority=priority,
            acceptance_criteria=criteria,
        )

    def _requirement_to_feature(self, req: ExtractedRequirement) -> Feature:
        """Convert an extracted requirement to a feature.

        Args:
            req: Requirement to convert.

        Returns:
            Feature object.
        """
        # Determine priority based on confidence
        priority = int(50 * req.confidence)

        # Partial implementations get slightly lower priority
        if req.status == "partial":
            priority -= 10

        return Feature(
            id=f"discovery-{req.id}",
            name=req.title,
            description=f"{req.description}\n\nSource: {req.source_file}",
            category=FeatureCategory.FUNCTIONAL,
            status=FeatureStatus.PENDING,
            priority=max(0, priority),
            acceptance_criteria=[
                "Feature is fully implemented",
                "Feature works as documented",
            ],
        )

    def save_backlog(self, backlog: Backlog, filename: str = "feature-list.json") -> Path:
        """Save the backlog to a file.

        Args:
            backlog: Backlog to save.
            filename: Output filename.

        Returns:
            Path to the saved file.
        """
        output_path = self.project_path / filename
        output_path.write_text(backlog.model_dump_json(indent=2), encoding="utf-8")
        return output_path

    def merge_backlogs(
        self,
        base: Backlog,
        incoming: Backlog,
        prefer_incoming: bool = False,
    ) -> Backlog:
        """Merge two backlogs together.

        Args:
            base: Base backlog.
            incoming: Incoming backlog to merge.
            prefer_incoming: Whether to prefer incoming on conflicts.

        Returns:
            Merged backlog.
        """
        merged = Backlog(
            project_name=base.project_name,
            project_path=base.project_path,
            features=list(base.features),
            created_at=base.created_at,
        )

        existing_ids = {f.id for f in merged.features}

        for feature in incoming.features:
            if feature.id not in existing_ids:
                merged.features.append(feature)
                existing_ids.add(feature.id)
            elif prefer_incoming:
                # Replace existing feature
                merged.features = [
                    feature if f.id == feature.id else f
                    for f in merged.features
                ]

        # Sort by priority
        merged.features.sort(key=lambda f: f.priority, reverse=True)
        merged.last_updated = datetime.now()

        return merged
