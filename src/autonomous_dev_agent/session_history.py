"""Session history management for persistent tracking.

Stores session records in a JSON file for cost tracking, analytics,
and dashboard display.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .models import SessionRecord, SessionOutcome, UsageStats


class CostSummary(BaseModel):
    """Summary of costs over a time period."""
    total_cost_usd: float = 0.0
    total_sessions: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0

    # Breakdown by model
    cost_by_model: dict[str, float] = Field(default_factory=dict)
    sessions_by_model: dict[str, int] = Field(default_factory=dict)

    # Breakdown by outcome
    sessions_by_outcome: dict[str, int] = Field(default_factory=dict)

    # Time period
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class SessionHistory:
    """Manages persistent session history.

    Stores records in .ada_session_history.json in the project directory.
    """

    DEFAULT_FILENAME = ".ada_session_history.json"

    def __init__(self, project_path: Path, filename: Optional[str] = None):
        """Initialize session history.

        Args:
            project_path: Path to the project directory
            filename: Custom filename (defaults to .ada_session_history.json)
        """
        self.project_path = Path(project_path)
        self.filename = filename or self.DEFAULT_FILENAME
        self._history_file = self.project_path / self.filename
        self._records: list[SessionRecord] = []
        self._load()

    def _load(self) -> None:
        """Load session history from disk."""
        if not self._history_file.exists():
            self._records = []
            return

        try:
            data = json.loads(self._history_file.read_text())
            if isinstance(data, list):
                self._records = [SessionRecord.model_validate(r) for r in data]
            elif isinstance(data, dict) and "sessions" in data:
                self._records = [SessionRecord.model_validate(r) for r in data["sessions"]]
            else:
                self._records = []
        except (json.JSONDecodeError, Exception) as e:
            print(f"[SessionHistory] Warning: Could not load history: {e}")
            self._records = []

    def _save(self) -> None:
        """Save session history to disk."""
        data = [r.model_dump(mode="json") for r in self._records]
        self._history_file.write_text(json.dumps(data, indent=2, default=str))

    def add_record(self, record: SessionRecord) -> None:
        """Add a session record.

        Args:
            record: Session record to add
        """
        self._records.append(record)
        self._save()

    def update_record(self, session_id: str, **updates) -> bool:
        """Update an existing session record.

        Args:
            session_id: Session ID to update
            **updates: Fields to update

        Returns:
            True if record was found and updated
        """
        for i, record in enumerate(self._records):
            if record.session_id == session_id:
                # Create updated record
                record_dict = record.model_dump()
                record_dict.update(updates)
                self._records[i] = SessionRecord.model_validate(record_dict)
                self._save()
                return True
        return False

    def get_record(self, session_id: str) -> Optional[SessionRecord]:
        """Get a specific session record.

        Args:
            session_id: Session ID to find

        Returns:
            SessionRecord if found, None otherwise
        """
        for record in self._records:
            if record.session_id == session_id:
                return record
        return None

    def get_all_records(self) -> list[SessionRecord]:
        """Get all session records."""
        return list(self._records)

    def get_recent_records(self, count: int = 10) -> list[SessionRecord]:
        """Get the most recent session records.

        Args:
            count: Maximum number of records to return

        Returns:
            List of most recent records (newest first)
        """
        sorted_records = sorted(
            self._records,
            key=lambda r: r.started_at,
            reverse=True
        )
        return sorted_records[:count]

    def get_records_for_feature(self, feature_id: str) -> list[SessionRecord]:
        """Get all session records for a specific feature.

        Args:
            feature_id: Feature ID to filter by

        Returns:
            List of records for the feature
        """
        return [r for r in self._records if r.feature_id == feature_id]

    def get_records_by_outcome(self, outcome: SessionOutcome) -> list[SessionRecord]:
        """Get all session records with a specific outcome.

        Args:
            outcome: Outcome to filter by

        Returns:
            List of matching records
        """
        return [r for r in self._records if r.outcome == outcome]

    def get_records_in_range(
        self,
        start: datetime,
        end: Optional[datetime] = None
    ) -> list[SessionRecord]:
        """Get session records within a time range.

        Args:
            start: Start of the time range
            end: End of the time range (defaults to now)

        Returns:
            List of records in the range
        """
        end = end or datetime.now()
        return [
            r for r in self._records
            if start <= r.started_at <= end
        ]

    def get_cost_summary(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> CostSummary:
        """Calculate cost summary for a time period.

        Args:
            start: Start of the period (defaults to all time)
            end: End of the period (defaults to now)

        Returns:
            CostSummary with aggregated data
        """
        if start:
            records = self.get_records_in_range(start, end)
        else:
            records = self._records

        summary = CostSummary(
            period_start=start,
            period_end=end or datetime.now()
        )

        for record in records:
            summary.total_cost_usd += record.cost_usd
            summary.total_sessions += 1
            summary.total_input_tokens += record.input_tokens
            summary.total_output_tokens += record.output_tokens
            summary.total_cache_read_tokens += record.cache_read_tokens
            summary.total_cache_write_tokens += record.cache_write_tokens

            # By model
            if record.model:
                summary.cost_by_model[record.model] = (
                    summary.cost_by_model.get(record.model, 0.0) + record.cost_usd
                )
                summary.sessions_by_model[record.model] = (
                    summary.sessions_by_model.get(record.model, 0) + 1
                )

            # By outcome
            outcome_str = record.outcome.value
            summary.sessions_by_outcome[outcome_str] = (
                summary.sessions_by_outcome.get(outcome_str, 0) + 1
            )

        return summary

    def get_daily_cost_summary(self, days: int = 7) -> list[CostSummary]:
        """Get cost summaries for each day in a period.

        Args:
            days: Number of days to include

        Returns:
            List of CostSummary, one per day (most recent first)
        """
        summaries = []
        now = datetime.now()

        for i in range(days):
            day_end = now - timedelta(days=i)
            day_start = day_end.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            summary = self.get_cost_summary(day_start, day_end)
            summaries.append(summary)

        return summaries

    def get_total_usage_stats(self) -> UsageStats:
        """Get total usage stats across all sessions.

        Returns:
            Aggregated UsageStats
        """
        stats = UsageStats()

        for record in self._records:
            stats = stats + record.to_usage_stats()

        return stats

    def get_feature_cost(self, feature_id: str) -> float:
        """Get total cost for a specific feature.

        Args:
            feature_id: Feature ID

        Returns:
            Total cost in USD
        """
        records = self.get_records_for_feature(feature_id)
        return sum(r.cost_usd for r in records)

    def get_feature_stats(self, feature_id: str) -> dict:
        """Get statistics for a specific feature.

        Args:
            feature_id: Feature ID

        Returns:
            Dict with feature statistics
        """
        records = self.get_records_for_feature(feature_id)

        if not records:
            return {
                "feature_id": feature_id,
                "total_sessions": 0,
                "total_cost_usd": 0.0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "outcomes": {},
            }

        outcomes = {}
        for r in records:
            outcome = r.outcome.value
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

        return {
            "feature_id": feature_id,
            "total_sessions": len(records),
            "total_cost_usd": sum(r.cost_usd for r in records),
            "total_input_tokens": sum(r.input_tokens for r in records),
            "total_output_tokens": sum(r.output_tokens for r in records),
            "outcomes": outcomes,
            "first_session": min(r.started_at for r in records),
            "last_session": max(r.started_at for r in records),
        }

    def clear(self) -> None:
        """Clear all session history."""
        self._records = []
        self._save()

    def count(self) -> int:
        """Get the number of session records."""
        return len(self._records)


def create_session_record(
    session_id: str,
    feature_id: Optional[str] = None,
    model: str = "",
    outcome: SessionOutcome = SessionOutcome.SUCCESS,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cost_usd: float = 0.0,
    files_changed: Optional[list[str]] = None,
    commit_hash: Optional[str] = None,
    error_message: Optional[str] = None,
    error_category: Optional[str] = None,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None
) -> SessionRecord:
    """Helper function to create a session record.

    Args:
        session_id: Unique session identifier
        feature_id: Feature being worked on
        model: Model used
        outcome: How the session ended
        input_tokens: Input tokens consumed
        output_tokens: Output tokens generated
        cache_read_tokens: Cache read tokens
        cache_write_tokens: Cache write tokens
        cost_usd: Session cost
        files_changed: List of modified files
        commit_hash: Commit hash if committed
        error_message: Error message if failed
        error_category: Error category if failed
        started_at: Session start time
        ended_at: Session end time

    Returns:
        SessionRecord instance
    """
    return SessionRecord(
        session_id=session_id,
        feature_id=feature_id,
        started_at=started_at or datetime.now(),
        ended_at=ended_at,
        outcome=outcome,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        model=model,
        cost_usd=cost_usd,
        files_changed=files_changed or [],
        commit_hash=commit_hash,
        error_message=error_message,
        error_category=error_category
    )
