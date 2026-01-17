"""Tests for the data models."""

import pytest
from datetime import datetime

from autonomous_dev_agent.models import (
    Feature, Backlog, FeatureStatus, FeatureCategory
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
