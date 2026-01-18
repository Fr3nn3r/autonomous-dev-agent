"""Tests for cost tracking functionality."""

import pytest

from autonomous_dev_agent.cost_tracker import (
    CostTracker,
    PRICING,
    MODEL_ALIASES,
    estimate_session_cost,
)
from autonomous_dev_agent.models import UsageStats


class TestCostTracker:
    """Test CostTracker class."""

    def test_initialization_default_model(self):
        """Test CostTracker initializes with default model."""
        tracker = CostTracker()
        assert tracker.model == "claude-sonnet-4-20250514"

    def test_initialization_with_model(self):
        """Test CostTracker initializes with specified model."""
        tracker = CostTracker("claude-opus-4-5-20251101")
        assert tracker.model == "claude-opus-4-5-20251101"

    def test_initialization_with_alias(self):
        """Test CostTracker resolves model aliases."""
        tracker = CostTracker("opus")
        assert tracker.model == "claude-opus-4-5-20251101"

        tracker = CostTracker("sonnet")
        assert tracker.model == "claude-sonnet-4-20250514"

        tracker = CostTracker("haiku")
        assert tracker.model == "claude-haiku-4-5-20251001"

    def test_get_pricing_known_model(self):
        """Test getting pricing for known models."""
        tracker = CostTracker()

        pricing = tracker.get_pricing("claude-opus-4-5-20251101")
        assert pricing["input"] == 15.00
        assert pricing["output"] == 75.00
        assert pricing["cache_read"] == 1.50

        pricing = tracker.get_pricing("claude-sonnet-4-20250514")
        assert pricing["input"] == 3.00
        assert pricing["output"] == 15.00

    def test_get_pricing_unknown_model_defaults_to_sonnet(self):
        """Test unknown model defaults to Sonnet pricing."""
        tracker = CostTracker()
        pricing = tracker.get_pricing("unknown-model-123")
        assert pricing == PRICING["claude-sonnet-4-20250514"]

    def test_calculate_cost_basic(self):
        """Test basic cost calculation."""
        tracker = CostTracker("claude-sonnet-4-20250514")

        # 1M input tokens at $3/M = $3
        cost = tracker.calculate_cost(input_tokens=1_000_000)
        assert cost == 3.0

        # 1M output tokens at $15/M = $15
        cost = tracker.calculate_cost(output_tokens=1_000_000)
        assert cost == 15.0

    def test_calculate_cost_combined(self):
        """Test cost calculation with multiple token types."""
        tracker = CostTracker("claude-sonnet-4-20250514")

        # 100K input ($0.30) + 50K output ($0.75) = $1.05
        cost = tracker.calculate_cost(
            input_tokens=100_000,
            output_tokens=50_000
        )
        assert abs(cost - 1.05) < 0.001

    def test_calculate_cost_with_cache(self):
        """Test cost calculation including cache tokens."""
        tracker = CostTracker("claude-sonnet-4-20250514")

        # Cache read is much cheaper than regular input
        cost_cached = tracker.calculate_cost(cache_read_tokens=1_000_000)
        cost_regular = tracker.calculate_cost(input_tokens=1_000_000)

        assert cost_cached < cost_regular
        assert cost_cached == 0.30  # $0.30 per 1M cache read

    def test_calculate_cost_opus_model(self):
        """Test cost calculation for Opus model (more expensive)."""
        tracker = CostTracker("claude-opus-4-5-20251101")

        # 1M input tokens at $15/M = $15
        cost = tracker.calculate_cost(input_tokens=1_000_000)
        assert cost == 15.0

        # 1M output tokens at $75/M = $75
        cost = tracker.calculate_cost(output_tokens=1_000_000)
        assert cost == 75.0

    def test_track_usage_returns_stats(self):
        """Test track_usage returns UsageStats with cost."""
        tracker = CostTracker("claude-sonnet-4-20250514")

        stats = tracker.track_usage(
            input_tokens=10_000,
            output_tokens=5_000
        )

        assert isinstance(stats, UsageStats)
        assert stats.input_tokens == 10_000
        assert stats.output_tokens == 5_000
        assert stats.model == "claude-sonnet-4-20250514"
        assert stats.cost_usd > 0

    def test_track_usage_accumulates(self):
        """Test that track_usage accumulates in cumulative stats."""
        tracker = CostTracker("claude-sonnet-4-20250514")

        tracker.track_usage(input_tokens=10_000, output_tokens=5_000)
        tracker.track_usage(input_tokens=20_000, output_tokens=10_000)

        cumulative = tracker.get_cumulative_stats()
        assert cumulative.input_tokens == 30_000
        assert cumulative.output_tokens == 15_000

    def test_reset_clears_cumulative(self):
        """Test reset clears cumulative stats."""
        tracker = CostTracker()

        tracker.track_usage(input_tokens=10_000, output_tokens=5_000)
        assert tracker.get_cumulative_stats().input_tokens == 10_000

        tracker.reset()
        assert tracker.get_cumulative_stats().input_tokens == 0

    def test_format_cost(self):
        """Test cost formatting."""
        assert CostTracker.format_cost(0.001) == "$0.0010"
        assert CostTracker.format_cost(0.12) == "$0.12"
        assert CostTracker.format_cost(1.50) == "$1.50"
        assert CostTracker.format_cost(123.45) == "$123.45"

    def test_format_tokens(self):
        """Test token count formatting."""
        assert CostTracker.format_tokens(500) == "500"
        assert CostTracker.format_tokens(1500) == "1.5K"
        assert CostTracker.format_tokens(15000) == "15.0K"
        assert CostTracker.format_tokens(1_500_000) == "1.50M"


class TestCliOutputParsing:
    """Test CLI output parsing functionality."""

    def test_parse_cli_output_empty(self):
        """Test parsing empty output returns None."""
        result = CostTracker.parse_cli_output("")
        assert result is None

        result = CostTracker.parse_cli_output(None)
        assert result is None

    def test_parse_cli_output_with_tokens(self):
        """Test parsing output with token counts."""
        output = "Tokens: 1234 in / 5678 out"
        stats = CostTracker.parse_cli_output(output)

        assert stats is not None
        assert stats.input_tokens == 1234
        assert stats.output_tokens == 5678

    def test_parse_cli_output_with_cost(self):
        """Test parsing output with cost."""
        output = "Session complete. Cost: $0.12"
        stats = CostTracker.parse_cli_output(output)

        assert stats is not None
        assert stats.cost_usd == 0.12

    def test_parse_cli_output_with_model(self):
        """Test parsing output with model name."""
        output = "Using claude-sonnet-4-20250514 for this session"
        stats = CostTracker.parse_cli_output(output)

        assert stats is not None
        assert "claude-sonnet" in stats.model

    def test_parse_cli_output_no_match(self):
        """Test parsing output with no recognizable patterns."""
        output = "Hello world, this is just some text"
        stats = CostTracker.parse_cli_output(output)
        assert stats is None


class TestEstimateSessionCost:
    """Test session cost estimation function."""

    def test_estimate_basic_session(self):
        """Test basic session cost estimation."""
        cost = estimate_session_cost(
            model="claude-sonnet-4-20250514",
            estimated_turns=10,
            avg_input_per_turn=5000,
            avg_output_per_turn=2000
        )

        # 10 turns * 5000 input = 50K input
        # 10 turns * 2000 output = 20K output
        # 50K input at $3/M = $0.15
        # 20K output at $15/M = $0.30
        # Total = $0.45
        expected = (50_000 / 1_000_000) * 3.0 + (20_000 / 1_000_000) * 15.0
        assert abs(cost - expected) < 0.001

    def test_estimate_opus_session_more_expensive(self):
        """Test that Opus sessions are estimated more expensive."""
        sonnet_cost = estimate_session_cost(model="claude-sonnet-4-20250514")
        opus_cost = estimate_session_cost(model="claude-opus-4-5-20251101")

        assert opus_cost > sonnet_cost


class TestUsageStatsAddition:
    """Test UsageStats addition operator."""

    def test_add_usage_stats(self):
        """Test adding two UsageStats together."""
        stats1 = UsageStats(
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            model="claude-sonnet-4-20250514"
        )
        stats2 = UsageStats(
            input_tokens=200,
            output_tokens=100,
            cost_usd=0.02,
            model="claude-sonnet-4-20250514"
        )

        combined = stats1 + stats2

        assert combined.input_tokens == 300
        assert combined.output_tokens == 150
        assert combined.cost_usd == 0.03
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
