"""Tests for session management classes.

Tests cover:
- BaseSession abstract class
- SDKSession implementation
- MockSession implementation
- create_session factory function
- SessionManager class
"""

import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from autonomous_dev_agent.models import (
    HarnessConfig, SessionState, ErrorCategory
)
from autonomous_dev_agent.session import (
    SessionResult,
    BaseSession,
    SDKSession,
    MockSession,
    create_session,
    SessionManager,
)


# =============================================================================
# Tests for SessionResult
# =============================================================================

class TestSessionResult:
    """Tests for SessionResult model."""

    def test_create_minimal(self):
        """Should create with minimal required fields."""
        result = SessionResult(
            session_id="test-123",
            success=True,
            context_usage_percent=50.0
        )
        assert result.session_id == "test-123"
        assert result.success is True
        assert result.context_usage_percent == 50.0

    def test_default_values(self):
        """Should have correct default values."""
        result = SessionResult(
            session_id="test",
            success=True,
            context_usage_percent=0.0
        )
        assert result.error_message is None
        assert result.error_category is None
        assert result.feature_completed is False
        assert result.handoff_requested is False
        assert result.summary is None
        assert result.files_changed == []
        assert result.started_at is None
        assert result.ended_at is None
        assert result.model == ""
        assert result.raw_output is None
        assert result.raw_error is None

    def test_with_error(self):
        """Should store error information."""
        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=0.0,
            error_message="Something went wrong",
            error_category=ErrorCategory.TRANSIENT
        )
        assert result.success is False
        assert result.error_message == "Something went wrong"
        assert result.error_category == ErrorCategory.TRANSIENT

    def test_with_timing(self):
        """Should store timing information."""
        start = datetime.now()
        end = datetime.now()
        result = SessionResult(
            session_id="test",
            success=True,
            context_usage_percent=0.0,
            started_at=start,
            ended_at=end
        )
        assert result.started_at == start
        assert result.ended_at == end


# =============================================================================
# Tests for BaseSession (via concrete implementations)
# =============================================================================

class TestBaseSessionStateMangement:
    """Tests for BaseSession state management functionality."""

    def test_save_and_load_state(self, tmp_path):
        """Should save and load session state."""
        config = HarnessConfig()
        session = MockSession(config, tmp_path, "test-session")

        state = SessionState(
            session_id="test-session",
            current_feature_id="feature-1",
            context_usage_percent=45.0,
            last_commit_hash="abc123"
        )

        session.save_state(state)
        loaded = session.load_state()

        assert loaded is not None
        assert loaded.session_id == "test-session"
        assert loaded.current_feature_id == "feature-1"
        assert loaded.context_usage_percent == 45.0

    def test_load_state_returns_none_when_missing(self, tmp_path):
        """Should return None when state file doesn't exist."""
        config = HarnessConfig()
        session = MockSession(config, tmp_path)

        assert session.load_state() is None

    def test_clear_state(self, tmp_path):
        """Should clear session state file."""
        config = HarnessConfig()
        session = MockSession(config, tmp_path)

        state = SessionState(session_id="test")
        session.save_state(state)
        assert session.load_state() is not None

        session.clear_state()
        assert session.load_state() is None

    def test_generates_session_id_if_not_provided(self, tmp_path):
        """Should generate session ID if not provided."""
        config = HarnessConfig()
        session = MockSession(config, tmp_path)

        assert session.session_id is not None
        assert session.session_id.startswith("session_")

    def test_uses_provided_session_id(self, tmp_path):
        """Should use provided session ID."""
        config = HarnessConfig()
        session = MockSession(config, tmp_path, "my-custom-id")

        assert session.session_id == "my-custom-id"


# =============================================================================
# Tests for SDKSession
# =============================================================================

class TestSDKSession:
    """Tests for SDK session implementation."""

    def test_initialization(self, tmp_path):
        """Should initialize with correct config."""
        config = HarnessConfig()
        session = SDKSession(config, tmp_path, "sdk-test")

        assert session.config == config
        assert session.project_path == tmp_path
        assert session.session_id == "sdk-test"

    @pytest.mark.asyncio
    async def test_falls_back_to_mock_without_sdk(self, tmp_path):
        """Should fall back to mock when SDK not installed."""
        config = HarnessConfig()
        session = SDKSession(config, tmp_path)

        # SDK import will fail, triggering mock fallback
        with patch.dict('sys.modules', {'claude_agent_sdk': None}):
            result = await session._run_session("test prompt")

            # Mock session should succeed
            assert result.success is True
            assert "MOCK" in result.summary

    @pytest.mark.asyncio
    async def test_run_applies_timeout(self, tmp_path):
        """Should apply session timeout."""
        config = HarnessConfig(
            session_timeout_seconds=1
        )
        session = SDKSession(config, tmp_path)

        async def slow_session(*args, **kwargs):
            await asyncio.sleep(10)
            return SessionResult(session_id="test", success=True, context_usage_percent=0)

        with patch.object(session, '_run_session', side_effect=slow_session):
            result = await session.run("test prompt")

            assert result.success is False
            assert result.handoff_requested is True


# =============================================================================
# Tests for MockSession
# =============================================================================

class TestMockSession:
    """Tests for mock session implementation."""

    def test_initialization(self, tmp_path):
        """Should initialize correctly."""
        config = HarnessConfig()
        session = MockSession(config, tmp_path, "mock-test")

        assert session.session_id == "mock-test"

    @pytest.mark.asyncio
    async def test_run_returns_success(self, tmp_path):
        """Should return successful result."""
        config = HarnessConfig()
        session = MockSession(config, tmp_path)

        result = await session._run_session("test prompt")

        assert result.success is True
        assert "MOCK" in result.summary
        assert result.context_usage_percent == 25.0

    @pytest.mark.asyncio
    async def test_run_with_full_session_flow(self, tmp_path):
        """Should work with full run() flow including timing."""
        config = HarnessConfig(session_timeout_seconds=60)
        session = MockSession(config, tmp_path)

        result = await session.run("test prompt")

        assert result.success is True
        assert result.started_at is not None
        assert result.ended_at is not None
        assert result.model == config.model


# =============================================================================
# Tests for create_session factory
# =============================================================================

class TestCreateSessionFactory:
    """Tests for create_session factory function."""

    def test_creates_sdk_session(self, tmp_path):
        """Should create SDKSession."""
        config = HarnessConfig()
        session = create_session(config, tmp_path, "test-id")

        assert isinstance(session, SDKSession)
        assert session.session_id == "test-id"

    def test_generates_session_id_if_not_provided(self, tmp_path):
        """Should generate session ID if not provided."""
        config = HarnessConfig()
        session = create_session(config, tmp_path)

        assert session.session_id is not None
        assert len(session.session_id) > 0


# =============================================================================
# Tests for SessionManager
# =============================================================================

class TestSessionManager:
    """Tests for SessionManager class."""

    def test_initialization(self, tmp_path):
        """Should initialize with config and path."""
        config = HarnessConfig()
        manager = SessionManager(config, tmp_path)

        assert manager.config == config
        assert manager.project_path == tmp_path
        assert manager.session_count == 0
        assert manager.current_session is None

    def test_create_session_increments_count(self, tmp_path):
        """Should increment session count on each create."""
        config = HarnessConfig()
        manager = SessionManager(config, tmp_path)

        session1 = manager.create_session()
        assert manager.session_count == 1

        session2 = manager.create_session()
        assert manager.session_count == 2

    def test_create_session_returns_sdk_session(self, tmp_path):
        """Should create SDKSession."""
        config = HarnessConfig()
        manager = SessionManager(config, tmp_path)
        session = manager.create_session()
        assert isinstance(session, SDKSession)

    def test_create_session_sets_current_session(self, tmp_path):
        """Should set current_session on create."""
        config = HarnessConfig()
        manager = SessionManager(config, tmp_path)

        assert manager.current_session is None
        session = manager.create_session()
        assert manager.current_session is session

    def test_create_session_generates_unique_ids(self, tmp_path):
        """Should generate unique session IDs."""
        config = HarnessConfig()
        manager = SessionManager(config, tmp_path)

        session1 = manager.create_session()
        session2 = manager.create_session()

        assert session1.session_id != session2.session_id
        assert "s001" in session1.session_id
        assert "s002" in session2.session_id

    def test_should_continue_respects_max_sessions(self, tmp_path):
        """Should return False when max_sessions reached."""
        config = HarnessConfig(max_sessions=2)
        manager = SessionManager(config, tmp_path)

        assert manager.should_continue() is True
        manager.create_session()
        assert manager.should_continue() is True
        manager.create_session()
        assert manager.should_continue() is False

    def test_should_continue_unlimited_when_no_max(self, tmp_path):
        """Should return True indefinitely when max_sessions is None."""
        config = HarnessConfig(max_sessions=None)
        manager = SessionManager(config, tmp_path)

        for _ in range(10):
            manager.create_session()

        assert manager.should_continue() is True

    def test_get_recovery_state_returns_state(self, tmp_path):
        """Should return recovery state if exists."""
        config = HarnessConfig()
        manager = SessionManager(config, tmp_path)

        # Create and save state manually
        state = SessionState(
            session_id="recovery-test",
            current_feature_id="feature-1",
            context_usage_percent=70.0
        )
        state_file = tmp_path / ".ada_session_state.json"
        state_file.write_text(state.model_dump_json())

        recovered = manager.get_recovery_state()
        assert recovered is not None
        assert recovered.session_id == "recovery-test"
        assert recovered.current_feature_id == "feature-1"

    def test_get_recovery_state_returns_none_when_no_state(self, tmp_path):
        """Should return None when no recovery state exists."""
        config = HarnessConfig()
        manager = SessionManager(config, tmp_path)

        assert manager.get_recovery_state() is None


# =============================================================================
# Integration Tests
# =============================================================================

class TestSessionIntegration:
    """Integration tests for session classes working together."""

    @pytest.mark.asyncio
    async def test_full_mock_session_workflow(self, tmp_path):
        """Test complete workflow with mock session."""
        config = HarnessConfig()
        manager = SessionManager(config, tmp_path)

        # Create session
        session = manager.create_session()
        assert manager.session_count == 1

        # Save state
        state = SessionState(
            session_id=session.session_id,
            current_feature_id="test-feature"
        )
        session.save_state(state)

        # Recover state
        recovered = manager.get_recovery_state()
        assert recovered.current_feature_id == "test-feature"

        # Clean up
        session.clear_state()
        assert manager.get_recovery_state() is None

    @pytest.mark.asyncio
    async def test_session_result_includes_timing(self, tmp_path):
        """Test that session results include timing information."""
        config = HarnessConfig(session_timeout_seconds=60)
        session = MockSession(config, tmp_path)

        before = datetime.now()
        result = await session.run("test prompt")
        after = datetime.now()

        assert result.started_at is not None
        assert result.ended_at is not None
        assert before <= result.started_at <= after
        assert result.started_at <= result.ended_at <= after

    def test_session_types_share_state_file_location(self, tmp_path):
        """All session types should use same state file location."""
        config = HarnessConfig()

        sdk = SDKSession(config, tmp_path)
        mock = MockSession(config, tmp_path)

        # All should use the same state file
        assert sdk._state_file == mock._state_file
        assert sdk._state_file == tmp_path / ".ada_session_state.json"
