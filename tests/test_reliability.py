"""Tests for reliability features (Phase 1).

Tests cover:
- R4: Error Classification
- R1: Retry Logic with Exponential Backoff
- R2: Test Validation
- R8: Session Timeout
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio

from autonomous_dev_agent.models import (
    ErrorCategory, RetryConfig, HarnessConfig
)
from autonomous_dev_agent.session import classify_error, SessionResult


class TestErrorClassification:
    """Tests for R4: Error Classification."""

    def test_classify_billing_error(self):
        """Billing errors should be classified as BILLING."""
        assert classify_error("Credit balance is too low") == ErrorCategory.BILLING
        assert classify_error("insufficient credits") == ErrorCategory.BILLING
        assert classify_error("billing issue") == ErrorCategory.BILLING
        assert classify_error("payment required") == ErrorCategory.BILLING
        assert classify_error("quota exceeded") == ErrorCategory.BILLING

    def test_classify_auth_error(self):
        """Authentication errors should be classified as AUTH."""
        assert classify_error("authentication failed") == ErrorCategory.AUTH
        assert classify_error("unauthorized access") == ErrorCategory.AUTH
        assert classify_error("401 Unauthorized") == ErrorCategory.AUTH
        assert classify_error("invalid api key") == ErrorCategory.AUTH
        assert classify_error("403 forbidden") == ErrorCategory.AUTH

    def test_classify_rate_limit_error(self):
        """Rate limit errors should be classified as RATE_LIMIT."""
        assert classify_error("rate limit exceeded") == ErrorCategory.RATE_LIMIT
        assert classify_error("429 Too Many Requests") == ErrorCategory.RATE_LIMIT
        assert classify_error("too many requests") == ErrorCategory.RATE_LIMIT
        assert classify_error("throttled") == ErrorCategory.RATE_LIMIT

    def test_classify_sdk_crash_error(self):
        """SDK crash errors should be classified as SDK_CRASH."""
        assert classify_error("exit code 1") == ErrorCategory.SDK_CRASH
        assert classify_error("exit code: 1") == ErrorCategory.SDK_CRASH
        assert classify_error("process exited with code 1") == ErrorCategory.SDK_CRASH

    def test_classify_heap_corruption_error(self):
        """Windows heap corruption (0xC0000374) should be classified as SDK_CRASH."""
        # Decimal form
        assert classify_error("exit code 3221225786") == ErrorCategory.SDK_CRASH
        assert classify_error("exit code: 3221225786") == ErrorCategory.SDK_CRASH
        assert classify_error("process exited with code 3221225786") == ErrorCategory.SDK_CRASH
        # Hex form (case insensitive)
        assert classify_error("0xC0000374") == ErrorCategory.SDK_CRASH
        assert classify_error("0xc0000374") == ErrorCategory.SDK_CRASH
        # Text form
        assert classify_error("heap corruption detected") == ErrorCategory.SDK_CRASH

    def test_classify_transient_error(self):
        """Network/timeout errors should be classified as TRANSIENT."""
        assert classify_error("connection timeout") == ErrorCategory.TRANSIENT
        assert classify_error("request timed out") == ErrorCategory.TRANSIENT
        assert classify_error("network unreachable") == ErrorCategory.TRANSIENT
        assert classify_error("500 Internal Server Error") == ErrorCategory.TRANSIENT
        assert classify_error("502 Bad Gateway") == ErrorCategory.TRANSIENT
        assert classify_error("503 Service Unavailable") == ErrorCategory.TRANSIENT
        assert classify_error("504 Gateway Timeout") == ErrorCategory.TRANSIENT

    def test_classify_unknown_error(self):
        """Unknown errors should be classified as UNKNOWN."""
        assert classify_error("something went wrong") == ErrorCategory.UNKNOWN
        assert classify_error("unexpected error") == ErrorCategory.UNKNOWN
        assert classify_error("") == ErrorCategory.UNKNOWN

    def test_classify_empty_error(self):
        """Empty or None error should be classified as UNKNOWN."""
        assert classify_error("") == ErrorCategory.UNKNOWN
        assert classify_error(None) == ErrorCategory.UNKNOWN

    def test_classify_case_insensitive(self):
        """Classification should be case-insensitive."""
        assert classify_error("CREDIT BALANCE") == ErrorCategory.BILLING
        assert classify_error("Rate Limit") == ErrorCategory.RATE_LIMIT
        assert classify_error("AUTHENTICATION") == ErrorCategory.AUTH


class TestRetryConfig:
    """Tests for RetryConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay_seconds == 5.0
        assert config.max_delay_seconds == 300.0
        assert config.exponential_base == 2.0
        assert config.jitter_factor == 0.1

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RetryConfig(
            max_retries=5,
            base_delay_seconds=10.0,
            max_delay_seconds=600.0
        )
        assert config.max_retries == 5
        assert config.base_delay_seconds == 10.0
        assert config.max_delay_seconds == 600.0

    def test_default_retryable_categories(self):
        """Test that default retryable categories are correct."""
        config = RetryConfig()
        assert ErrorCategory.TRANSIENT in config.retryable_categories
        assert ErrorCategory.RATE_LIMIT in config.retryable_categories
        assert ErrorCategory.SDK_CRASH in config.retryable_categories
        assert ErrorCategory.BILLING not in config.retryable_categories
        assert ErrorCategory.AUTH not in config.retryable_categories


class TestHarnessConfigReliability:
    """Tests for reliability-related HarnessConfig fields."""

    def test_test_command_default(self):
        """Test command should be None by default."""
        config = HarnessConfig()
        assert config.test_command is None

    def test_test_command_custom(self):
        """Test command can be set."""
        config = HarnessConfig(test_command="pytest")
        assert config.test_command == "pytest"

    def test_session_timeout_default(self):
        """Session timeout should default to 30 minutes."""
        config = HarnessConfig()
        assert config.session_timeout_seconds == 1800

    def test_session_timeout_custom(self):
        """Session timeout can be customized."""
        config = HarnessConfig(session_timeout_seconds=3600)
        assert config.session_timeout_seconds == 3600

    def test_retry_config_default(self):
        """Retry config should use defaults."""
        config = HarnessConfig()
        assert config.retry.max_retries == 3

    def test_retry_config_custom(self):
        """Retry config can be customized."""
        config = HarnessConfig(retry=RetryConfig(max_retries=5))
        assert config.retry.max_retries == 5


class TestSessionResultWithErrorCategory:
    """Tests for SessionResult with error_category field."""

    def test_session_result_with_error_category(self):
        """SessionResult should include error_category."""
        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=50.0,
            error_message="Rate limited",
            error_category=ErrorCategory.RATE_LIMIT
        )
        assert result.error_category == ErrorCategory.RATE_LIMIT

    def test_session_result_without_error_category(self):
        """SessionResult error_category should be optional."""
        result = SessionResult(
            session_id="test",
            success=True,
            context_usage_percent=50.0
        )
        assert result.error_category is None


class TestRetryLogicHelpers:
    """Tests for retry logic helper functions in harness."""

    @pytest.fixture
    def harness_mock(self):
        """Create a mock harness for testing."""
        from autonomous_dev_agent.harness import AutonomousHarness
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            # Create minimal backlog file
            (path / "feature-list.json").write_text('{"project_name": "test", "project_path": ".", "features": []}')

            harness = AutonomousHarness(path)
            yield harness

    def test_calculate_retry_delay_first_attempt(self, harness_mock):
        """First retry should use base delay."""
        config = RetryConfig(base_delay_seconds=5.0, jitter_factor=0.0)
        delay = harness_mock._orchestrator._calculate_retry_delay(0, config)
        assert delay == 5.0

    def test_calculate_retry_delay_exponential(self, harness_mock):
        """Delay should increase exponentially."""
        config = RetryConfig(
            base_delay_seconds=5.0,
            exponential_base=2.0,
            jitter_factor=0.0
        )
        # attempt 0: 5 * 2^0 = 5
        assert harness_mock._orchestrator._calculate_retry_delay(0, config) == 5.0
        # attempt 1: 5 * 2^1 = 10
        assert harness_mock._orchestrator._calculate_retry_delay(1, config) == 10.0
        # attempt 2: 5 * 2^2 = 20
        assert harness_mock._orchestrator._calculate_retry_delay(2, config) == 20.0

    def test_calculate_retry_delay_capped(self, harness_mock):
        """Delay should be capped at max_delay_seconds."""
        config = RetryConfig(
            base_delay_seconds=100.0,
            exponential_base=2.0,
            max_delay_seconds=150.0,
            jitter_factor=0.0
        )
        # attempt 2: 100 * 2^2 = 400, capped to 150
        delay = harness_mock._orchestrator._calculate_retry_delay(2, config)
        assert delay == 150.0

    def test_should_retry_on_transient_error(self, harness_mock):
        """Should retry on transient errors."""
        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=50.0,
            error_category=ErrorCategory.TRANSIENT
        )
        assert harness_mock._orchestrator._should_retry(result, 0, harness_mock.config.retry) is True

    def test_should_retry_on_rate_limit(self, harness_mock):
        """Should retry on rate limit errors."""
        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=50.0,
            error_category=ErrorCategory.RATE_LIMIT
        )
        assert harness_mock._orchestrator._should_retry(result, 0, harness_mock.config.retry) is True

    def test_should_not_retry_on_billing_error(self, harness_mock):
        """Should not retry on billing errors."""
        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=50.0,
            error_category=ErrorCategory.BILLING
        )
        assert harness_mock._orchestrator._should_retry(result, 0, harness_mock.config.retry) is False

    def test_should_not_retry_on_auth_error(self, harness_mock):
        """Should not retry on auth errors."""
        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=50.0,
            error_category=ErrorCategory.AUTH
        )
        assert harness_mock._orchestrator._should_retry(result, 0, harness_mock.config.retry) is False

    def test_should_not_retry_after_max_attempts(self, harness_mock):
        """Should not retry after max attempts."""
        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=50.0,
            error_category=ErrorCategory.TRANSIENT
        )
        # At attempt 3 with max_retries=3, should not retry
        assert harness_mock._orchestrator._should_retry(result, 3, harness_mock.config.retry) is False

    def test_should_not_retry_on_success(self, harness_mock):
        """Should not retry successful sessions."""
        result = SessionResult(
            session_id="test",
            success=True,
            context_usage_percent=50.0
        )
        assert harness_mock._orchestrator._should_retry(result, 0, harness_mock.config.retry) is False

    def test_should_not_retry_on_handoff(self, harness_mock):
        """Should not retry when handoff is requested."""
        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=70.0,
            handoff_requested=True
        )
        assert harness_mock._orchestrator._should_retry(result, 0, harness_mock.config.retry) is False

    def test_should_retry_unknown_error_once(self, harness_mock):
        """Should retry unknown errors once."""
        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=50.0,
            error_category=ErrorCategory.UNKNOWN
        )
        # First attempt should retry
        assert harness_mock._orchestrator._should_retry(result, 0, harness_mock.config.retry) is True
        # Second attempt should not retry
        assert harness_mock._orchestrator._should_retry(result, 1, harness_mock.config.retry) is False
