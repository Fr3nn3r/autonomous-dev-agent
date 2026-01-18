"""Tests for the data models."""

import pytest
from datetime import datetime

from autonomous_dev_agent.models import (
    Feature, Backlog, FeatureStatus, FeatureCategory, QualityGates, HarnessConfig
)


class TestFeature:
    def test_create_feature(self):
        feature = Feature(
            id="test-feature",
            name="Test Feature",
            description="A test feature"
        )
        assert feature.id == "test-feature"
        assert feature.status == FeatureStatus.PENDING
        assert feature.category == FeatureCategory.FUNCTIONAL

    def test_feature_with_criteria(self):
        feature = Feature(
            id="test",
            name="Test",
            description="Test",
            acceptance_criteria=["Criterion 1", "Criterion 2"]
        )
        assert len(feature.acceptance_criteria) == 2


class TestBacklog:
    def test_create_backlog(self):
        backlog = Backlog(
            project_name="Test Project",
            project_path="/tmp/test"
        )
        assert backlog.project_name == "Test Project"
        assert len(backlog.features) == 0

    def test_get_next_feature_priority(self):
        backlog = Backlog(
            project_name="Test",
            project_path="/tmp",
            features=[
                Feature(id="low", name="Low", description="", priority=1),
                Feature(id="high", name="High", description="", priority=10),
                Feature(id="medium", name="Medium", description="", priority=5),
            ]
        )
        next_feature = backlog.get_next_feature()
        assert next_feature.id == "high"

    def test_get_next_feature_respects_dependencies(self):
        backlog = Backlog(
            project_name="Test",
            project_path="/tmp",
            features=[
                Feature(id="base", name="Base", description="", priority=1),
                Feature(id="dependent", name="Dependent", description="", priority=10, depends_on=["base"]),
            ]
        )
        # Highest priority is "dependent" but it depends on "base"
        next_feature = backlog.get_next_feature()
        assert next_feature.id == "base"

    def test_get_next_feature_in_progress_first(self):
        backlog = Backlog(
            project_name="Test",
            project_path="/tmp",
            features=[
                Feature(id="pending", name="Pending", description="", priority=10),
                Feature(id="in-progress", name="In Progress", description="", priority=1, status=FeatureStatus.IN_PROGRESS),
            ]
        )
        next_feature = backlog.get_next_feature()
        assert next_feature.id == "in-progress"

    def test_is_complete(self):
        backlog = Backlog(
            project_name="Test",
            project_path="/tmp",
            features=[
                Feature(id="f1", name="F1", description="", status=FeatureStatus.COMPLETED),
                Feature(id="f2", name="F2", description="", status=FeatureStatus.COMPLETED),
            ]
        )
        assert backlog.is_complete() is True

    def test_is_not_complete(self):
        backlog = Backlog(
            project_name="Test",
            project_path="/tmp",
            features=[
                Feature(id="f1", name="F1", description="", status=FeatureStatus.COMPLETED),
                Feature(id="f2", name="F2", description="", status=FeatureStatus.PENDING),
            ]
        )
        assert backlog.is_complete() is False

    def test_mark_feature_started(self):
        backlog = Backlog(
            project_name="Test",
            project_path="/tmp",
            features=[
                Feature(id="f1", name="F1", description=""),
            ]
        )
        backlog.mark_feature_started("f1")
        assert backlog.features[0].status == FeatureStatus.IN_PROGRESS
        assert backlog.features[0].started_at is not None
        assert backlog.features[0].sessions_spent == 1

    def test_mark_feature_completed(self):
        backlog = Backlog(
            project_name="Test",
            project_path="/tmp",
            features=[
                Feature(id="f1", name="F1", description="", status=FeatureStatus.IN_PROGRESS),
            ]
        )
        backlog.mark_feature_completed("f1", "Done in session 1")
        assert backlog.features[0].status == FeatureStatus.COMPLETED
        assert backlog.features[0].completed_at is not None
        assert "Done in session 1" in backlog.features[0].implementation_notes


class TestQualityGates:
    def test_create_default_quality_gates(self):
        gates = QualityGates()
        assert gates.require_tests is False
        assert gates.max_file_lines is None
        assert gates.security_checklist == []
        assert gates.lint_command is None
        assert gates.type_check_command is None
        assert gates.custom_validators == []

    def test_create_quality_gates_with_all_options(self):
        gates = QualityGates(
            require_tests=True,
            max_file_lines=400,
            security_checklist=[
                "Sanitize user input",
                "No hardcoded secrets"
            ],
            lint_command="ruff check .",
            type_check_command="pyright",
            custom_validators=["./scripts/check-migrations.sh"]
        )
        assert gates.require_tests is True
        assert gates.max_file_lines == 400
        assert len(gates.security_checklist) == 2
        assert gates.lint_command == "ruff check ."
        assert gates.type_check_command == "pyright"
        assert len(gates.custom_validators) == 1

    def test_feature_with_quality_gates(self):
        gates = QualityGates(
            require_tests=True,
            max_file_lines=300
        )
        feature = Feature(
            id="auth",
            name="User Auth",
            description="Implement authentication",
            quality_gates=gates
        )
        assert feature.quality_gates is not None
        assert feature.quality_gates.require_tests is True
        assert feature.quality_gates.max_file_lines == 300

    def test_feature_without_quality_gates(self):
        feature = Feature(
            id="simple",
            name="Simple Feature",
            description="A simple feature"
        )
        assert feature.quality_gates is None


class TestHarnessConfigQualityGates:
    def test_default_quality_gates_none(self):
        config = HarnessConfig()
        assert config.default_quality_gates is None
        assert config.progress_rotation_threshold_kb == 50
        assert config.progress_keep_entries == 100

    def test_harness_config_with_default_gates(self):
        gates = QualityGates(
            require_tests=True,
            lint_command="ruff check ."
        )
        config = HarnessConfig(default_quality_gates=gates)
        assert config.default_quality_gates is not None
        assert config.default_quality_gates.require_tests is True

    def test_custom_rotation_settings(self):
        config = HarnessConfig(
            progress_rotation_threshold_kb=100,
            progress_keep_entries=50
        )
        assert config.progress_rotation_threshold_kb == 100
        assert config.progress_keep_entries == 50
