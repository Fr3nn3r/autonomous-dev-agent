"""Discovery module for analyzing existing codebases.

This module provides tools to:
- Analyze codebase structure and detect languages/frameworks (analyzer.py)
- Check for best practices compliance (best_practices.py)
- Identify test coverage gaps (test_analyzer.py)
- Track discovery state for incremental analysis (tracker.py)
- Perform AI-powered code review (reviewer.py)
- Extract requirements from documentation (requirements.py)
- Generate backlog items from discovered issues (backlog_generator.py)
"""

from .analyzer import CodebaseAnalyzer
from .best_practices import BestPracticesChecker
from .test_analyzer import TestGapAnalyzer
from .tracker import DiscoveryTracker
from .backlog_generator import BacklogGenerator

__all__ = [
    "CodebaseAnalyzer",
    "BestPracticesChecker",
    "TestGapAnalyzer",
    "DiscoveryTracker",
    "BacklogGenerator",
]
