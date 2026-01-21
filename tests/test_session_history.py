"""Tests for session history management."""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from autonomous_dev_agent.session_history import (
    SessionHistory,
    TokenSummary,
    create_session_record,
)
from autonomous_dev_agent.models import SessionRecord, SessionOutcome, UsageStats


@pytest.fixture
def temp_project_path(tmp_path):
    """Create a temporary project directory."""
    return tmp_path


@pytest.fixture
def session_history(temp_project_path):
    """Create a SessionHistory instance with a temporary path."""
    return SessionHistory(temp_project_path)


class TestSessionHistory:
    """Test SessionHistory class."""

    def test_initialization_creates_empty_history(self, session_history):
        """Test that a new SessionHistory starts empty."""
        assert session_history.count() == 0
        assert session_history.get_all_records() == []

    def test_add_record(self, session_history):
        """Test adding a session record."""
        record = create_session_record(
            session_id="test-001",
            feature_id="feature-1",
            model="claude-sonnet-4-20250514",
            outcome=SessionOutcome.SUCCESS,
            input_tokens=1000,
            output_tokens=500,
        )

        session_history.add_record(record)

        assert session_history.count() == 1
        retrieved = session_history.get_record("test-001")
        assert retrieved is not None
        assert retrieved.session_id == "test-001"
        assert retrieved.feature_id == "feature-1"

    def test_persistence_to_disk(self, temp_project_path, session_history):
        """Test that records are persisted to disk."""
        record = create_session_record(
            session_id="test-001",
            feature_id="feature-1",
            outcome=SessionOutcome.SUCCESS
        )
        session_history.add_record(record)

        # Create new instance from same path
        new_history = SessionHistory(temp_project_path)
        assert new_history.count() == 1
        assert new_history.get_record("test-001") is not None

    def test_get_record_not_found(self, session_history):
        """Test getting a non-existent record returns None."""
        assert session_history.get_record("nonexistent") is None

    def test_get_recent_records(self, session_history):
        """Test getting recent records in reverse chronological order."""
        # Add records with different timestamps
        for i in range(5):
            record = create_session_record(
                session_id=f"test-{i:03d}",
                started_at=datetime.now() - timedelta(hours=5-i)
            )
            session_history.add_record(record)

        recent = session_history.get_recent_records(3)
        assert len(recent) == 3
        # Most recent should be first
        assert recent[0].session_id == "test-004"
        assert recent[1].session_id == "test-003"
        assert recent[2].session_id == "test-002"

    def test_get_records_for_feature(self, session_history):
        """Test filtering records by feature ID."""
        session_history.add_record(create_session_record(
            session_id="test-001", feature_id="feature-a"
        ))
        session_history.add_record(create_session_record(
            session_id="test-002", feature_id="feature-b"
        ))
        session_history.add_record(create_session_record(
            session_id="test-003", feature_id="feature-a"
        ))

        feature_a_records = session_history.get_records_for_feature("feature-a")
        assert len(feature_a_records) == 2
        assert all(r.feature_id == "feature-a" for r in feature_a_records)

    def test_get_records_by_outcome(self, session_history):
        """Test filtering records by outcome."""
        session_history.add_record(create_session_record(
            session_id="test-001", outcome=SessionOutcome.SUCCESS
        ))
        session_history.add_record(create_session_record(
            session_id="test-002", outcome=SessionOutcome.FAILURE
        ))
        session_history.add_record(create_session_record(
            session_id="test-003", outcome=SessionOutcome.SUCCESS
        ))

        successes = session_history.get_records_by_outcome(SessionOutcome.SUCCESS)
        assert len(successes) == 2

        failures = session_history.get_records_by_outcome(SessionOutcome.FAILURE)
        assert len(failures) == 1

    def test_get_records_in_range(self, session_history):
        """Test getting records within a time range."""
        now = datetime.now()

        session_history.add_record(create_session_record(
            session_id="old", started_at=now - timedelta(days=10)
        ))
        session_history.add_record(create_session_record(
            session_id="recent", started_at=now - timedelta(hours=1)
        ))
        session_history.add_record(create_session_record(
            session_id="newest", started_at=now
        ))

        # Last 24 hours
        recent = session_history.get_records_in_range(now - timedelta(days=1))
        assert len(recent) == 2
        assert "old" not in [r.session_id for r in recent]

    def test_update_record(self, session_history):
        """Test updating an existing record."""
        session_history.add_record(create_session_record(
            session_id="test-001",
            outcome=SessionOutcome.HANDOFF,
            input_tokens=1000
        ))

        # Update the record
        updated = session_history.update_record(
            "test-001",
            outcome=SessionOutcome.SUCCESS,
            input_tokens=1500
        )
        assert updated is True

        record = session_history.get_record("test-001")
        assert record.outcome == SessionOutcome.SUCCESS
        assert record.input_tokens == 1500

    def test_update_nonexistent_record(self, session_history):
        """Test updating a non-existent record returns False."""
        updated = session_history.update_record("nonexistent", input_tokens=1000)
        assert updated is False

    def test_clear(self, session_history):
        """Test clearing all history."""
        session_history.add_record(create_session_record(session_id="test-001"))
        session_history.add_record(create_session_record(session_id="test-002"))

        assert session_history.count() == 2

        session_history.clear()
        assert session_history.count() == 0


class TestTokenSummary:
    """Test token summary calculations."""

    def test_get_token_summary_empty(self, session_history):
        """Test token summary on empty history."""
        summary = session_history.get_token_summary()

        assert summary.total_tokens == 0
        assert summary.total_sessions == 0
        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0

    def test_get_token_summary_aggregation(self, session_history):
        """Test that token summary aggregates correctly."""
        session_history.add_record(create_session_record(
            session_id="test-001",
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            outcome=SessionOutcome.SUCCESS
        ))
        session_history.add_record(create_session_record(
            session_id="test-002",
            model="claude-sonnet-4-20250514",
            input_tokens=2000,
            output_tokens=1000,
            outcome=SessionOutcome.HANDOFF
        ))

        summary = session_history.get_token_summary()

        assert summary.total_sessions == 2
        assert summary.total_input_tokens == 3000
        assert summary.total_output_tokens == 1500
        assert summary.total_tokens == 4500

    def test_tokens_by_model(self, session_history):
        """Test token breakdown by model."""
        session_history.add_record(create_session_record(
            session_id="test-001",
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500
        ))
        session_history.add_record(create_session_record(
            session_id="test-002",
            model="claude-opus-4-5-20251101",
            input_tokens=5000,
            output_tokens=2500
        ))
        session_history.add_record(create_session_record(
            session_id="test-003",
            model="claude-sonnet-4-20250514",
            input_tokens=1500,
            output_tokens=750
        ))

        summary = session_history.get_token_summary()

        # Sonnet: 1000+500 + 1500+750 = 3750
        assert summary.tokens_by_model["claude-sonnet-4-20250514"] == 3750
        # Opus: 5000+2500 = 7500
        assert summary.tokens_by_model["claude-opus-4-5-20251101"] == 7500
        assert summary.sessions_by_model["claude-sonnet-4-20250514"] == 2
        assert summary.sessions_by_model["claude-opus-4-5-20251101"] == 1

    def test_sessions_by_outcome(self, session_history):
        """Test session count breakdown by outcome."""
        session_history.add_record(create_session_record(
            session_id="test-001", outcome=SessionOutcome.SUCCESS
        ))
        session_history.add_record(create_session_record(
            session_id="test-002", outcome=SessionOutcome.SUCCESS
        ))
        session_history.add_record(create_session_record(
            session_id="test-003", outcome=SessionOutcome.FAILURE
        ))
        session_history.add_record(create_session_record(
            session_id="test-004", outcome=SessionOutcome.HANDOFF
        ))

        summary = session_history.get_token_summary()

        assert summary.sessions_by_outcome["success"] == 2
        assert summary.sessions_by_outcome["failure"] == 1
        assert summary.sessions_by_outcome["handoff"] == 1

    def test_token_summary_with_date_range(self, session_history):
        """Test token summary with date filtering."""
        now = datetime.now()

        session_history.add_record(create_session_record(
            session_id="old",
            input_tokens=100000,
            output_tokens=50000,
            started_at=now - timedelta(days=30)
        ))
        session_history.add_record(create_session_record(
            session_id="recent",
            input_tokens=1000,
            output_tokens=500,
            started_at=now - timedelta(hours=1)
        ))

        # Last 7 days only
        summary = session_history.get_token_summary(
            start=now - timedelta(days=7)
        )

        assert summary.total_sessions == 1
        assert summary.total_tokens == 1500


class TestFeatureStats:
    """Test feature-specific statistics."""

    def test_get_feature_tokens(self, session_history):
        """Test getting total tokens for a feature."""
        session_history.add_record(create_session_record(
            session_id="test-001", feature_id="feature-a", input_tokens=1000, output_tokens=500
        ))
        session_history.add_record(create_session_record(
            session_id="test-002", feature_id="feature-b", input_tokens=2000, output_tokens=1000
        ))
        session_history.add_record(create_session_record(
            session_id="test-003", feature_id="feature-a", input_tokens=1500, output_tokens=750
        ))

        assert session_history.get_feature_tokens("feature-a") == 3750  # 1000+500+1500+750
        assert session_history.get_feature_tokens("feature-b") == 3000  # 2000+1000
        assert session_history.get_feature_tokens("feature-c") == 0

    def test_get_feature_stats(self, session_history):
        """Test getting comprehensive stats for a feature."""
        session_history.add_record(create_session_record(
            session_id="test-001",
            feature_id="feature-a",
            input_tokens=1000,
            output_tokens=500,
            outcome=SessionOutcome.HANDOFF
        ))
        session_history.add_record(create_session_record(
            session_id="test-002",
            feature_id="feature-a",
            input_tokens=2000,
            output_tokens=1000,
            outcome=SessionOutcome.SUCCESS
        ))

        stats = session_history.get_feature_stats("feature-a")

        assert stats["feature_id"] == "feature-a"
        assert stats["total_sessions"] == 2
        assert stats["total_input_tokens"] == 3000
        assert stats["total_output_tokens"] == 1500
        assert stats["outcomes"]["handoff"] == 1
        assert stats["outcomes"]["success"] == 1

    def test_get_feature_stats_empty(self, session_history):
        """Test feature stats for non-existent feature."""
        stats = session_history.get_feature_stats("nonexistent")

        assert stats["total_sessions"] == 0


class TestSessionRecordModel:
    """Test SessionRecord model functionality."""

    def test_duration_seconds(self):
        """Test session duration calculation."""
        start = datetime.now()
        end = start + timedelta(minutes=5, seconds=30)

        record = SessionRecord(
            session_id="test",
            started_at=start,
            ended_at=end,
            outcome=SessionOutcome.SUCCESS
        )

        duration = record.duration_seconds
        assert duration is not None
        assert abs(duration - 330) < 1  # 5:30 = 330 seconds

    def test_duration_seconds_no_end(self):
        """Test duration is None when session not ended."""
        record = SessionRecord(
            session_id="test",
            started_at=datetime.now(),
            outcome=SessionOutcome.SUCCESS
        )

        assert record.duration_seconds is None

    def test_to_usage_stats(self):
        """Test converting record to UsageStats."""
        record = SessionRecord(
            session_id="test",
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=200,
            model="claude-sonnet-4-20250514",
            outcome=SessionOutcome.SUCCESS
        )

        stats = record.to_usage_stats()

        assert isinstance(stats, UsageStats)
        assert stats.input_tokens == 1000
        assert stats.output_tokens == 500
        assert stats.cache_read_tokens == 200
        assert stats.model == "claude-sonnet-4-20250514"


class TestCreateSessionRecord:
    """Test the create_session_record helper function."""

    def test_create_basic_record(self):
        """Test creating a basic session record."""
        record = create_session_record(
            session_id="test-001",
            feature_id="feature-1",
            model="claude-sonnet-4-20250514",
            outcome=SessionOutcome.SUCCESS
        )

        assert record.session_id == "test-001"
        assert record.feature_id == "feature-1"
        assert record.model == "claude-sonnet-4-20250514"
        assert record.outcome == SessionOutcome.SUCCESS

    def test_create_record_with_all_fields(self):
        """Test creating a record with all fields populated."""
        now = datetime.now()
        record = create_session_record(
            session_id="test-001",
            feature_id="feature-1",
            model="claude-opus-4-5-20251101",
            outcome=SessionOutcome.FAILURE,
            input_tokens=5000,
            output_tokens=2500,
            cache_read_tokens=1000,
            cache_write_tokens=500,
            files_changed=["file1.py", "file2.py"],
            commit_hash="abc123",
            error_message="Test error",
            error_category="transient",
            started_at=now,
            ended_at=now + timedelta(minutes=10)
        )

        assert record.input_tokens == 5000
        assert record.output_tokens == 2500
        assert record.cache_read_tokens == 1000
        assert record.cache_write_tokens == 500
        assert record.files_changed == ["file1.py", "file2.py"]
        assert record.commit_hash == "abc123"
        assert record.error_message == "Test error"
        assert record.error_category == "transient"

    def test_create_record_defaults(self):
        """Test that create_session_record has sensible defaults."""
        record = create_session_record(session_id="test-001")

        assert record.feature_id is None
        assert record.model == ""
        assert record.outcome == SessionOutcome.SUCCESS
        assert record.input_tokens == 0
        assert record.output_tokens == 0
        assert record.files_changed == []


class TestDailyTokenSummary:
    """Test daily token summary functionality."""

    def test_get_daily_token_summary(self, session_history):
        """Test getting daily token summaries."""
        now = datetime.now()

        # Add records for different days
        for i in range(3):
            session_history.add_record(create_session_record(
                session_id=f"day-{i}",
                input_tokens=1000 * (i + 1),
                output_tokens=500 * (i + 1),
                started_at=now - timedelta(days=i, hours=1)
            ))

        summaries = session_history.get_daily_token_summary(days=3)

        assert len(summaries) == 3
        # Today should be first (i=0, tokens=1500)
        assert summaries[0].total_tokens == 1500
        # Yesterday (i=1, tokens=3000)
        assert summaries[1].total_tokens == 3000
        # Day before (i=2, tokens=4500)
        assert summaries[2].total_tokens == 4500

    def test_get_total_usage_stats(self, session_history):
        """Test getting total usage stats across all sessions."""
        session_history.add_record(create_session_record(
            session_id="test-001",
            input_tokens=1000,
            output_tokens=500,
        ))
        session_history.add_record(create_session_record(
            session_id="test-002",
            input_tokens=2000,
            output_tokens=1000,
        ))

        stats = session_history.get_total_usage_stats()

        assert stats.input_tokens == 3000
        assert stats.output_tokens == 1500
