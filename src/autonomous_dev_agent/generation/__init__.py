"""Generation module for AI-driven feature backlog creation.

This module provides tools to:
- Parse application specification files (spec_parser.py)
- Generate feature backlogs using Claude AI (feature_generator.py)
"""

from .spec_parser import SpecParser, ParsedSpec
from .feature_generator import FeatureGenerator, GeneratedBacklog, GenerationError

__all__ = [
    "SpecParser",
    "ParsedSpec",
    "FeatureGenerator",
    "GeneratedBacklog",
    "GenerationError",
]
