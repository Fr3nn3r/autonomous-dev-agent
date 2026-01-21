"""Tests for token tracking functionality."""

import pytest

from autonomous_dev_agent.token_tracker import (
    TokenTracker,
    TokenSummary,
    MODEL_ALIASES,
    format_tokens,
)
from autonomous_dev_agent.models import UsageStats


class TestTokenTracker:
    """Test TokenTracker class."""

    def test_initialization_default_model(self):
        """Test TokenTracker initializes with default model."""
        tracker = TokenTracker()
        assert tracker.model == "claude-sonnet-4-20250514"

    def test_initialization_with_model(self):
        """Test TokenTracker initializes with specified model."""
        tracker = TokenTracker("claude-opus-4-5-20251101")
        assert tracker.model == "claude-opus-4-5-20251101"

    def test_initialization_with_alias(self):
        """Test TokenTracker resolves model aliases."""
        tracker = TokenTracker("opus")
        assert tracker.model == "claude-opus-4-5-20251101"

        tracker = TokenTracker("sonnet")
        assert tracker.model == "claude-sonnet-4-20250514"

        tracker = TokenTracker("haiku")
        assert tracker.model == "claude-haiku-4-5-20251001"

    def test_track_usage_returns_stats(self):
        """Test track_usage returns UsageStats."""
        tracker = TokenTracker("claude-sonnet-4-20250514")

        stats = tracker.track_usage(
            input_tokens=10_000,
            output_tokens=5_000
        )

        assert isinstance(stats, UsageStats)
        assert stats.input_tokens == 10_000
        assert stats.output_tokens == 5_000
        assert stats.model == "claude-sonnet-4-20250514"

    def test_track_usage_accumulates(self):
        """Test that track_usage accumulates in cumulative stats."""
        tracker = TokenTracker("claude-sonnet-4-20250514")

        tracker.track_usage(input_tokens=10_000, output_tokens=5_000)
        tracker.track_usage(input_tokens=20_000, output_tokens=10_000)

        cumulative = tracker.get_cumulative_stats()
        assert cumulative.input_tokens == 30_000
        assert cumulative.output_tokens == 15_000

    def test_track_usage_with_cache_tokens(self):
        """Test tracking cache tokens."""
        tracker = TokenTracker()

        stats = tracker.track_usage(
            input_tokens=10_000,
            output_tokens=5_000,
            cache_read_tokens=3_000,
            cache_write_tokens=2_000
        )

        assert stats.cache_read_tokens == 3_000
        assert stats.cache_write_tokens == 2_000

        cumulative = tracker.get_cumulative_stats()
        assert cumulative.cache_read_tokens == 3_000
        assert cumulative.cache_write_tokens == 2_000

    def test_reset_clears_cumulative(self):
        """Test reset clears cumulative stats."""
        tracker = TokenTracker()

        tracker.track_usage(input_tokens=10_000, output_tokens=5_000)
        assert tracker.get_cumulative_stats().input_tokens == 10_000

        tracker.reset()
        assert tracker.get_cumulative_stats().input_tokens == 0

    def test_format_tokens_static_method(self):
        """Test token count formatting."""
        assert TokenTracker.format_tokens(500) == "500"
        assert TokenTracker.format_tokens(1500) == "1.5K"
        assert TokenTracker.format_tokens(15000) == "15.0K"
        assert TokenTracker.format_tokens(1_500_000) == "1.50M"


class TestFormatTokensFunction:
    """Test the format_tokens function."""

    def test_format_small_numbers(self):
        """Test formatting small token counts."""
        assert format_tokens(0) == "0"
        assert format_tokens(1) == "1"
        assert format_tokens(999) == "999"

    def test_format_thousands(self):
        """Test formatting thousands of tokens."""
        assert format_tokens(1000) == "1.0K"
        assert format_tokens(1500) == "1.5K"
        assert format_tokens(99999) == "100.0K"

    def test_format_millions(self):
        """Test formatting millions of tokens."""
        assert format_tokens(1_000_000) == "1.00M"
        assert format_tokens(1_500_000) == "1.50M"
        assert format_tokens(10_000_000) == "10.00M"


class TestTokenSummary:
    """Test TokenSummary dataclass."""

    def test_total_tokens_property(self):
        """Test total_tokens property calculates sum."""
        summary = TokenSummary(
            total_input_tokens=10_000,
            total_output_tokens=5_000
        )
        assert summary.total_tokens == 15_000

    def test_default_values(self):
        """Test TokenSummary has sensible defaults."""
        summary = TokenSummary()
        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0
        assert summary.total_cache_read_tokens == 0
        assert summary.total_cache_write_tokens == 0
        assert summary.total_sessions == 0
        assert summary.tokens_by_model == {}
        assert summary.sessions_by_model == {}
        assert summary.sessions_by_outcome == {}


class TestCliOutputParsing:
    """Test CLI output parsing functionality."""

    def test_parse_cli_output_empty(self):
        """Test parsing empty output returns None."""
        result = TokenTracker.parse_cli_output("")
        assert result is None

        result = TokenTracker.parse_cli_output(None)
        assert result is None

    def test_parse_cli_output_with_tokens(self):
        """Test parsing output with token counts."""
        output = "Tokens: 1234 in / 5678 out"
        stats = TokenTracker.parse_cli_output(output)

        assert stats is not None
        assert stats.input_tokens == 1234
        assert stats.output_tokens == 5678

    def test_parse_cli_output_with_model(self):
        """Test parsing output with model name."""
        output = "Using claude-sonnet-4-20250514 for this session"
        stats = TokenTracker.parse_cli_output(output)

        assert stats is not None
        assert "claude-sonnet" in stats.model

    def test_parse_cli_output_no_match(self):
        """Test parsing output with no recognizable patterns."""
        output = "Hello world, this is just some text"
        stats = TokenTracker.parse_cli_output(output)
        assert stats is None


class TestUsageStatsAddition:
    """Test UsageStats addition operator."""

    def test_add_usage_stats(self):
        """Test adding two UsageStats together."""
        stats1 = UsageStats(
            input_tokens=100,
            output_tokens=50,
            model="claude-sonnet-4-20250514"
        )
        stats2 = UsageStats(
            input_tokens=200,
            output_tokens=100,
            model="claude-sonnet-4-20250514"
        )

        combined = stats1 + stats2

        assert combined.input_tokens == 300
        assert combined.output_tokens == 150
        assert combined.model == "claude-sonnet-4-20250514"

    def test_add_preserves_first_model(self):
        """Test that addition preserves the first non-empty model."""
        stats1 = UsageStats(model="opus")
        stats2 = UsageStats(model="sonnet")

        combined = stats1 + stats2
        assert combined.model == "opus"

        # If first is empty, use second
        stats1 = UsageStats(model="")
        combined = stats1 + stats2
        assert combined.model == "sonnet"

    def test_add_cache_tokens(self):
        """Test adding cache tokens."""
        stats1 = UsageStats(cache_read_tokens=100, cache_write_tokens=50)
        stats2 = UsageStats(cache_read_tokens=200, cache_write_tokens=100)

        combined = stats1 + stats2

        assert combined.cache_read_tokens == 300
        assert combined.cache_write_tokens == 150


class TestModelAliases:
    """Test model alias mapping."""

    def test_model_aliases_exist(self):
        """Test that expected model aliases exist."""
        assert "opus" in MODEL_ALIASES
        assert "sonnet" in MODEL_ALIASES
        assert "haiku" in MODEL_ALIASES

    def test_model_aliases_map_to_full_names(self):
        """Test that aliases map to full model names."""
        assert "claude-opus" in MODEL_ALIASES["opus"]
        assert "claude-sonnet" in MODEL_ALIASES["sonnet"]
        assert "claude-haiku" in MODEL_ALIASES["haiku"]


# Backwards compatibility alias test
class TestCostTrackerAlias:
    """Test CostTracker backwards compatibility alias."""

    def test_cost_tracker_is_token_tracker(self):
        """Test that CostTracker is an alias for TokenTracker."""
        from autonomous_dev_agent.token_tracker import CostTracker

        tracker = CostTracker()
        assert isinstance(tracker, TokenTracker)
