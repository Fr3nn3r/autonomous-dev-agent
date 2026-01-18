"""Adaptive model selection based on task complexity.

Selects the appropriate Claude model based on feature complexity,
dependencies, and keywords to balance cost and capability.
"""

import re
from typing import Optional

from .models import Feature, FeatureCategory


# Available models ordered from most to least capable
MODELS = {
    "opus": "claude-opus-4-5-20251101",
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}

# Default model for most tasks (cost-effective)
DEFAULT_MODEL = MODELS["sonnet"]

# Model for complex tasks (most capable)
COMPLEX_MODEL = MODELS["opus"]

# Model for simple tasks (fastest/cheapest)
SIMPLE_MODEL = MODELS["haiku"]

# Keywords that indicate complex tasks requiring Opus
COMPLEXITY_KEYWORDS = [
    # Architecture
    "architecture",
    "redesign",
    "restructure",
    "refactor",
    "migration",
    "overhaul",
    # Security
    "security",
    "authentication",
    "authorization",
    "encryption",
    "vulnerability",
    "oauth",
    "jwt",
    # Performance
    "optimize",
    "performance",
    "scalability",
    "caching",
    "concurrency",
    # Integration
    "integration",
    "api design",
    "webhook",
    "third-party",
    # Data
    "database schema",
    "data model",
    "schema migration",
    # Testing
    "test framework",
    "testing strategy",
]

# Keywords that indicate simple tasks (can use Haiku)
SIMPLE_KEYWORDS = [
    "typo",
    "comment",
    "readme",
    "documentation",
    "rename",
    "log",
    "print",
    "format",
    "lint",
    "style",
]

# Categories that typically need more capable models
COMPLEX_CATEGORIES = [
    FeatureCategory.REFACTOR,
    FeatureCategory.INFRASTRUCTURE,
]

# Categories that can typically use simpler models
SIMPLE_CATEGORIES = [
    FeatureCategory.DOCUMENTATION,
]


class ModelSelector:
    """Selects appropriate Claude model based on task complexity.

    Strategy:
    - Default to Sonnet (cost-effective, good for most tasks)
    - Escalate to Opus for complex architecture/security/refactor tasks
    - Use Haiku for simple documentation/typo fixes
    - Honor per-feature model overrides
    """

    def __init__(
        self,
        default_model: str = DEFAULT_MODEL,
        complex_model: str = COMPLEX_MODEL,
        simple_model: str = SIMPLE_MODEL
    ):
        """Initialize the model selector.

        Args:
            default_model: Model for typical tasks
            complex_model: Model for complex tasks
            simple_model: Model for simple tasks
        """
        self.default_model = default_model
        self.complex_model = complex_model
        self.simple_model = simple_model

    def select_model(self, feature: Feature) -> str:
        """Select the appropriate model for a feature.

        Args:
            feature: The feature to analyze

        Returns:
            Model name to use
        """
        # Honor explicit override
        if feature.model_override:
            return feature.model_override

        # Analyze complexity
        complexity_score = self._calculate_complexity_score(feature)

        # Select based on score
        if complexity_score >= 3:
            return self.complex_model
        elif complexity_score <= -2:
            return self.simple_model
        else:
            return self.default_model

    def _calculate_complexity_score(self, feature: Feature) -> int:
        """Calculate complexity score for a feature.

        Positive scores indicate complex tasks (use Opus)
        Negative scores indicate simple tasks (use Haiku)
        Near-zero scores use default (Sonnet)

        Args:
            feature: The feature to analyze

        Returns:
            Complexity score (higher = more complex)
        """
        score = 0

        # Check category
        if feature.category in COMPLEX_CATEGORIES:
            score += 2
        elif feature.category in SIMPLE_CATEGORIES:
            score -= 2

        # Check dependencies (more deps = more complex)
        dep_count = len(feature.depends_on)
        if dep_count >= 3:
            score += 2
        elif dep_count >= 1:
            score += 1

        # Check for complexity keywords in name and description
        text = f"{feature.name} {feature.description}".lower()
        for keyword in COMPLEXITY_KEYWORDS:
            if keyword in text:
                score += 1
                break  # Only add once per feature

        # Check for simple keywords
        for keyword in SIMPLE_KEYWORDS:
            if keyword in text:
                score -= 1
                break  # Only subtract once

        # Check acceptance criteria count (more = more complex)
        criteria_count = len(feature.acceptance_criteria)
        if criteria_count >= 5:
            score += 1
        elif criteria_count == 0:
            score -= 1

        # Check description length (longer = likely more complex)
        desc_length = len(feature.description)
        if desc_length > 500:
            score += 1
        elif desc_length < 50:
            score -= 1

        # Check sessions spent (repeated work suggests complexity)
        if feature.sessions_spent >= 3:
            score += 1

        return score

    def explain_selection(self, feature: Feature) -> dict:
        """Explain why a particular model was selected.

        Args:
            feature: The feature analyzed

        Returns:
            Dict with model, score, and explanation
        """
        model = self.select_model(feature)
        score = self._calculate_complexity_score(feature)

        reasons = []

        # Check for override
        if feature.model_override:
            reasons.append(f"Using explicit override: {feature.model_override}")
        else:
            # Explain the score
            if feature.category in COMPLEX_CATEGORIES:
                reasons.append(f"Category '{feature.category.value}' typically needs more capable model")
            elif feature.category in SIMPLE_CATEGORIES:
                reasons.append(f"Category '{feature.category.value}' can use simpler model")

            if len(feature.depends_on) >= 3:
                reasons.append(f"Has {len(feature.depends_on)} dependencies (complex)")
            elif len(feature.depends_on) >= 1:
                reasons.append(f"Has {len(feature.depends_on)} dependency(ies)")

            text = f"{feature.name} {feature.description}".lower()
            for keyword in COMPLEXITY_KEYWORDS:
                if keyword in text:
                    reasons.append(f"Contains complexity keyword: '{keyword}'")
                    break

            for keyword in SIMPLE_KEYWORDS:
                if keyword in text:
                    reasons.append(f"Contains simplicity keyword: '{keyword}'")
                    break

            if len(feature.acceptance_criteria) >= 5:
                reasons.append(f"Has {len(feature.acceptance_criteria)} acceptance criteria")

            if feature.sessions_spent >= 3:
                reasons.append(f"Already spent {feature.sessions_spent} sessions (stubborn task)")

        model_name = "Opus" if model == self.complex_model else (
            "Haiku" if model == self.simple_model else "Sonnet"
        )

        return {
            "model": model,
            "model_name": model_name,
            "complexity_score": score,
            "reasons": reasons,
            "recommendation": self._get_recommendation(score)
        }

    def _get_recommendation(self, score: int) -> str:
        """Get human-readable recommendation based on score."""
        if score >= 3:
            return "Complex task - using Opus for best results"
        elif score >= 1:
            return "Moderately complex - Sonnet should handle this well"
        elif score <= -2:
            return "Simple task - Haiku can handle this efficiently"
        else:
            return "Standard task - using default model"

    def get_model_info(self, model: str) -> dict:
        """Get information about a model.

        Args:
            model: Model name

        Returns:
            Dict with model information
        """
        # Map model names to short names
        short_name = "unknown"
        for name, full_name in MODELS.items():
            if full_name == model or name == model.lower():
                short_name = name
                break

        pricing_estimates = {
            "opus": {"input": "$15/M", "output": "$75/M", "description": "Most capable, highest cost"},
            "sonnet": {"input": "$3/M", "output": "$15/M", "description": "Balanced capability and cost"},
            "haiku": {"input": "$1/M", "output": "$5/M", "description": "Fastest, lowest cost"},
        }

        info = pricing_estimates.get(short_name, {
            "input": "Unknown",
            "output": "Unknown",
            "description": "Unknown model"
        })

        return {
            "model": model,
            "short_name": short_name,
            **info
        }


def select_model_for_feature(feature: Feature) -> str:
    """Convenience function to select model for a feature.

    Args:
        feature: The feature to analyze

    Returns:
        Model name to use
    """
    selector = ModelSelector()
    return selector.select_model(feature)


def explain_model_selection(feature: Feature) -> dict:
    """Convenience function to explain model selection.

    Args:
        feature: The feature to analyze

    Returns:
        Explanation dict
    """
    selector = ModelSelector()
    return selector.explain_selection(feature)
