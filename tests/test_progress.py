"""Tests for progress tracking and rotation."""

import pytest
from pathlib import Path
import tempfile
from datetime import datetime

from autonomous_dev_agent.progress import ProgressTracker
from autonomous_dev_agent.models import ProgressEntry, Feature


class TestProgressTracker:
    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_initialize_progress(self, temp_project):
        tracker = ProgressTracker(temp_project)
        tracker.initialize("Test Project")

        assert tracker.progress_file.exists()
        content = tracker.read_progress()
        assert "Test Project" in content
        assert "Created:" in content

    def test_initialize_does_not_overwrite(self, temp_project):
        tracker = ProgressTracker(temp_project)
        tracker.initialize("Project 1")
        original_content = tracker.read_progress()

        tracker.initialize("Project 2")
        new_content = tracker.read_progress()

        assert original_content == new_content
        assert "Project 1" in new_content

    def test_append_entry(self, temp_project):
        tracker = ProgressTracker(temp_project)
        tracker.initialize("Test")

        entry = ProgressEntry(
            session_id="session-1",
            feature_id="feat-1",
            action="session_started",
            summary="Starting work on feature"
        )
        tracker.append_entry(entry)

        content = tracker.read_progress()
        assert "session-1" in content
        assert "feat-1" in content
        assert "session_started" in content

    def test_read_recent_truncates(self, temp_project):
        tracker = ProgressTracker(temp_project)
        tracker.initialize("Test")

        # Add many entries
        for i in range(100):
            entry = ProgressEntry(
                session_id=f"session-{i}",
                action="test",
                summary=f"Entry {i}"
            )
            tracker.append_entry(entry)

        # Read only recent 10 lines
        recent = tracker.read_recent(lines=10)
        assert "[... earlier progress truncated ...]" in recent


class TestProgressRotation:
    @pytest.fixture
    def temp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_rotation_not_triggered_below_threshold(self, temp_project):
        # Use a high threshold so rotation doesn't trigger
        tracker = ProgressTracker(
            temp_project,
            rotation_threshold_kb=1000,
            keep_entries=5
        )
        tracker.initialize("Test")

        for i in range(10):
            entry = ProgressEntry(
                session_id=f"session-{i}",
                action="test",
                summary=f"Entry {i}"
            )
            tracker.append_entry(entry)

        # No archives should exist
        archives = tracker.get_archive_files()
        assert len(archives) == 0

    def test_rotation_triggered_above_threshold(self, temp_project):
        # Use a very low threshold so rotation triggers quickly
        tracker = ProgressTracker(
            temp_project,
            rotation_threshold_kb=1,  # 1KB threshold
            keep_entries=5
        )
        tracker.initialize("Test")

        # Add enough entries to exceed 1KB
        for i in range(50):
            entry = ProgressEntry(
                session_id=f"session-{i}",
                action="test",
                summary="X" * 100  # Make entries large
            )
            tracker.append_entry(entry)

        # Archive should be created
        archives = tracker.get_archive_files()
        assert len(archives) >= 1

    def test_rotation_keeps_recent_entries(self, temp_project):
        tracker = ProgressTracker(
            temp_project,
            rotation_threshold_kb=1,
            keep_entries=5
        )
        tracker.initialize("Test")

        # Add entries
        for i in range(50):
            entry = ProgressEntry(
                session_id=f"session-{i}",
                action="test",
                summary="X" * 100
            )
            tracker.append_entry(entry)

        # Check that recent entries are still in main file
        content = tracker.read_progress()
        # The most recent entries should still be there
        assert "session-49" in content or "session-48" in content

    def test_archive_file_contains_old_entries(self, temp_project):
        tracker = ProgressTracker(
            temp_project,
            rotation_threshold_kb=1,
            keep_entries=3
        )
        tracker.initialize("Test")

        # Add entries with identifiable markers
        for i in range(20):
            entry = ProgressEntry(
                session_id=f"marker-{i}",
                action="test",
                summary="X" * 100
            )
            tracker.append_entry(entry)

        archives = tracker.get_archive_files()
        if archives:
            archive_content = archives[0].read_text()
            # Earlier entries should be in archive
            assert "marker-0" in archive_content or "marker-1" in archive_content

    def test_rotation_adds_archive_reference(self, temp_project):
        tracker = ProgressTracker(
            temp_project,
            rotation_threshold_kb=1,
            keep_entries=3
        )
        tracker.initialize("Test")

        for i in range(20):
            entry = ProgressEntry(
                session_id=f"session-{i}",
                action="test",
                summary="X" * 100
            )
            tracker.append_entry(entry)

        content = tracker.read_progress()
        # Should mention archive file
        if tracker.get_archive_files():
            assert "archived to:" in content.lower() or "rotated:" in content.lower()


class TestLogMethods:
    @pytest.fixture
    def temp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_log_session_start(self, temp_project):
        tracker = ProgressTracker(temp_project)
        tracker.initialize("Test")

        feature = Feature(
            id="feat-1",
            name="Test Feature",
            description="A test feature",
            acceptance_criteria=["Criterion 1", "Criterion 2"]
        )
        tracker.log_session_start("session-1", feature)

        content = tracker.read_progress()
        assert "session_started" in content
        assert "Test Feature" in content
        assert "Criterion 1" in content

    def test_log_handoff(self, temp_project):
        tracker = ProgressTracker(temp_project)
        tracker.initialize("Test")

        tracker.log_handoff(
            session_id="session-1",
            feature_id="feat-1",
            summary="Completed part 1",
            files_changed=["src/main.py", "tests/test_main.py"],
            commit_hash="abc123",
            next_steps="Continue with part 2"
        )

        content = tracker.read_progress()
        assert "HANDOFF" in content
        assert "Completed part 1" in content
        assert "src/main.py" in content
        assert "abc123" in content
        assert "Continue with part 2" in content

    def test_log_feature_completed(self, temp_project):
        tracker = ProgressTracker(temp_project)
        tracker.initialize("Test")

        feature = Feature(
            id="feat-1",
            name="Test Feature",
            description="A test feature"
        )
        tracker.log_feature_completed(
            session_id="session-1",
            feature=feature,
            summary="All tests passing",
            commit_hash="def456"
        )

        content = tracker.read_progress()
        assert "COMPLETED" in content
        assert "Test Feature" in content
        assert "def456" in content
