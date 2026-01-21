"""Token tracking for Claude API usage.

Tracks token consumption across sessions. On a subscription model,
token usage is the meaningful metric - not dollar costs.
"""

import re
from typing import Optional
from dataclasses import dataclass

from .models import UsageStats


# Aliases for common model names
MODEL_ALIASES = {
    "opus": "claude-opus-4-5-20251101",
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}


@dataclass
class TokenSummary:
    """Summary of token consumption over a time period."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_sessions: int = 0

    # Breakdown by model
    tokens_by_model: dict[str, int] = None
    sessions_by_model: dict[str, int] = None

    # Breakdown by outcome
    sessions_by_outcome: dict[str, int] = None

    def __post_init__(self):
        if self.tokens_by_model is None:
            self.tokens_by_model = {}
        if self.sessions_by_model is None:
            self.sessions_by_model = {}
        if self.sessions_by_outcome is None:
            self.sessions_by_outcome = {}

    @property
    def total_tokens(self) -> int:
        """Get total tokens (input + output)."""
        return self.total_input_tokens + self.total_output_tokens


class TokenTracker:
    """Tracks token consumption for Claude API usage."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        """Initialize token tracker with a model.

        Args:
            model: Model name or alias
        """
        self.model = self._resolve_model(model)
        self._cumulative_stats = UsageStats(model=self.model)

    def _resolve_model(self, model: str) -> str:
        """Resolve model aliases to full model names."""
        return MODEL_ALIASES.get(model.lower(), model)

    def track_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        model: Optional[str] = None
    ) -> UsageStats:
        """Track token usage.

        Args:
            input_tokens: Input tokens consumed
            output_tokens: Output tokens generated
            cache_read_tokens: Tokens read from cache
            cache_write_tokens: Tokens written to cache
            model: Model name (uses instance model if not specified)

        Returns:
            UsageStats with token data
        """
        model = model or self.model

        stats = UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            model=model,
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

        # Try to find model name
        model_pattern = r"(claude-[a-z0-9\-]+)"
        model_match = re.search(model_pattern, output, re.IGNORECASE)
        if model_match:
            stats.model = model_match.group(1)
            found_any = True

        return stats if found_any else None

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


# Backwards compatibility alias
CostTracker = TokenTracker


def format_tokens(count: int) -> str:
    """Format token count for display.

    Args:
        count: Token count

    Returns:
        Formatted string (e.g., "1.2K" or "1.5M")
    """
    return TokenTracker.format_tokens(count)
