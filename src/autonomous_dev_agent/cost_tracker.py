"""Cost tracking for Claude API usage.

Calculates costs based on token usage and model pricing.
Also includes CLI output parsing to extract usage data when available.
"""

import re
from typing import Optional

from .models import UsageStats


# Pricing per 1 million tokens (as of 2025)
# https://www.anthropic.com/pricing
PRICING = {
    # Opus 4.5
    "claude-opus-4-5-20251101": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_write": 18.75,
    },
    # Sonnet 4
    "claude-sonnet-4-20250514": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    # Haiku 4.5
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_write": 1.25,
    },
    # Legacy models (for reference)
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    "claude-3-opus-20240229": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_write": 18.75,
    },
}

# Aliases for common model names
MODEL_ALIASES = {
    "opus": "claude-opus-4-5-20251101",
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}


class CostTracker:
    """Tracks and calculates costs for Claude API usage."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        """Initialize cost tracker with a model.

        Args:
            model: Model name or alias
        """
        self.model = self._resolve_model(model)
        self._cumulative_stats = UsageStats(model=self.model)

    def _resolve_model(self, model: str) -> str:
        """Resolve model aliases to full model names."""
        return MODEL_ALIASES.get(model.lower(), model)

    def get_pricing(self, model: Optional[str] = None) -> dict:
        """Get pricing for a model.

        Args:
            model: Model name (uses instance model if not specified)

        Returns:
            Dict with input, output, cache_read, cache_write prices per 1M tokens
        """
        model = self._resolve_model(model or self.model)

        if model in PRICING:
            return PRICING[model]

        # Default to Sonnet pricing if model unknown
        return PRICING["claude-sonnet-4-20250514"]

    def calculate_cost(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        model: Optional[str] = None
    ) -> float:
        """Calculate cost for a given token usage.

        Args:
            input_tokens: Input tokens consumed
            output_tokens: Output tokens generated
            cache_read_tokens: Tokens read from cache
            cache_write_tokens: Tokens written to cache
            model: Model name (uses instance model if not specified)

        Returns:
            Cost in USD
        """
        pricing = self.get_pricing(model)

        # Calculate cost (prices are per 1M tokens)
        cost = 0.0
        cost += (input_tokens / 1_000_000) * pricing["input"]
        cost += (output_tokens / 1_000_000) * pricing["output"]
        cost += (cache_read_tokens / 1_000_000) * pricing["cache_read"]
        cost += (cache_write_tokens / 1_000_000) * pricing["cache_write"]

        return round(cost, 6)

    def track_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        model: Optional[str] = None
    ) -> UsageStats:
        """Track token usage and calculate cost.

        Args:
            input_tokens: Input tokens consumed
            output_tokens: Output tokens generated
            cache_read_tokens: Tokens read from cache
            cache_write_tokens: Tokens written to cache
            model: Model name (uses instance model if not specified)

        Returns:
            UsageStats with calculated cost
        """
        model = model or self.model
        cost = self.calculate_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            model=model
        )

        stats = UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            model=model,
            cost_usd=cost
        )

        # Update cumulative stats
        self._cumulative_stats = self._cumulative_stats + stats

        return stats

    def get_cumulative_stats(self) -> UsageStats:
        """Get cumulative usage stats for this tracker."""
        return self._cumulative_stats

    def reset(self) -> None:
        """Reset cumulative stats."""
        self._cumulative_stats = UsageStats(model=self.model)

    @staticmethod
    def parse_cli_output(output: str) -> Optional[UsageStats]:
        """Parse Claude CLI output to extract usage statistics.

        The Claude CLI may include usage info in its output. This method
        attempts to parse it.

        Args:
            output: Raw CLI output string

        Returns:
            UsageStats if usage info found, None otherwise
        """
        if not output:
            return None

        # Pattern for usage summary in CLI output
        # Example: "Tokens: 1234 in / 5678 out"
        # Example: "Usage: input=1234, output=5678"
        # Example: "Cost: $0.12"

        stats = UsageStats()
        found_any = False

        # Try to find token counts
        patterns = [
            # "1234 input tokens" or "input: 1234 tokens"
            (r"(?:input[:\s]*)?(\d+)\s*(?:input\s*)?tokens?", "input_tokens"),
            # "5678 output tokens" or "output: 5678 tokens"
            (r"(?:output[:\s]*)?(\d+)\s*(?:output\s*)?tokens?", "output_tokens"),
            # "Tokens: X in / Y out" format
            (r"(\d+)\s*(?:in|input)", "input_tokens"),
            (r"(\d+)\s*(?:out|output)", "output_tokens"),
            # Cache tokens
            (r"cache[_\s]*read[:\s]*(\d+)", "cache_read_tokens"),
            (r"cache[_\s]*write[:\s]*(\d+)", "cache_write_tokens"),
        ]

        for pattern, attr in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                setattr(stats, attr, int(match.group(1)))
                found_any = True

        # Try to find cost
        cost_pattern = r"\$(\d+\.?\d*)"
        cost_match = re.search(cost_pattern, output)
        if cost_match:
            stats.cost_usd = float(cost_match.group(1))
            found_any = True

        # Try to find model name
        model_pattern = r"(claude-[a-z0-9\-]+)"
        model_match = re.search(model_pattern, output, re.IGNORECASE)
        if model_match:
            stats.model = model_match.group(1)
            found_any = True

        return stats if found_any else None

    @staticmethod
    def format_cost(cost_usd: float) -> str:
        """Format cost for display.

        Args:
            cost_usd: Cost in USD

        Returns:
            Formatted string (e.g., "$0.12" or "$1.23")
        """
        if cost_usd < 0.01:
            return f"${cost_usd:.4f}"
        elif cost_usd < 1.00:
            return f"${cost_usd:.2f}"
        else:
            return f"${cost_usd:.2f}"

    @staticmethod
    def format_tokens(count: int) -> str:
        """Format token count for display.

        Args:
            count: Token count

        Returns:
            Formatted string (e.g., "1.2K" or "1.5M")
        """
        if count < 1000:
            return str(count)
        elif count < 1_000_000:
            return f"{count / 1000:.1f}K"
        else:
            return f"{count / 1_000_000:.2f}M"


def estimate_session_cost(
    model: str = "claude-sonnet-4-20250514",
    estimated_turns: int = 10,
    avg_input_per_turn: int = 5000,
    avg_output_per_turn: int = 2000
) -> float:
    """Estimate cost for a session based on expected turns.

    Args:
        model: Model to use
        estimated_turns: Expected number of turns
        avg_input_per_turn: Average input tokens per turn
        avg_output_per_turn: Average output tokens per turn

    Returns:
        Estimated cost in USD
    """
    tracker = CostTracker(model)

    total_input = estimated_turns * avg_input_per_turn
    total_output = estimated_turns * avg_output_per_turn

    return tracker.calculate_cost(
        input_tokens=total_input,
        output_tokens=total_output
    )
