"""Tests for orchestration components.

Tests cover:
- SessionRecoveryManager
- FeatureCompletionHandler
- SessionOrchestrator
- Protocol compliance
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from autonomous_dev_agent.models import (
    HarnessConfig, SessionState, Feature, Backlog,
    FeatureCategory, FeatureStatus, ProgressEntry, SessionOutcome,
    QualityGates
)
from autonomous_dev_agent.session import SessionResult, MockSession, SessionManager
from autonomous_dev_agent.git_manager import GitStatus
from autonomous_dev_agent.orchestration import (
    SessionRecoveryManager,
    FeatureCompletionHandler,
    SessionOrchestrator,
)
from autonomous_dev_agent.protocols import GitOperations, ProgressLog


# =============================================================================
# Mock Implementations for Testing
# =============================================================================

class MockGitOperations:
    """Mock implementation of GitOperations protocol."""

    def __init__(self, has_changes: bool = False, last_commit: str = "abc123"):
        self._has_changes = has_changes
        self._last_commit = last_commit
        self.staged_called = False
        self.commit_called = False
        self.last_commit_message = None

    def is_git_repo(self) -> bool:
        return True

    def get_status(self):
        return GitStatus(
            branch="main",
            has_changes=self._has_changes,
            staged_files=[],
            modified_files=["file1.py"] if self._has_changes else [],
            untracked_files=[],
            last_commit_hash=self._last_commit,
            last_commit_message="Last commit"
        )

    def stage_all(self) -> None:
        self.staged_called = True

    def commit(self, message: str, allow_empty: bool = False) -> str:
        self.commit_called = True
        self.last_commit_message = message
        return "new123"

    def get_changed_files(self, since_commit=None) -> list:
        return ["file1.py"] if self._has_changes else []


class MockProgressLog:
    """Mock implementation of ProgressLog protocol."""

    def __init__(self):
        self.entries = []
        self.initialized_project = None

    def read_progress(self) -> str:
        return "Progress content"

    def read_recent(self, lines: int = 50) -> str:
        return "Recent progress"

    def append_entry(self, entry: ProgressEntry) -> None:
        self.entries.append(entry)

    def log_handoff(self, session_id, feature_id, summary, files_changed,
                   commit_hash=None, next_steps=None) -> None:
        self.entries.append(ProgressEntry(
            session_id=session_id,
            feature_id=feature_id,
            action="handoff",
            summary=summary
        ))

    def log_feature_completed(self, session_id, feature, summary, commit_hash=None) -> None:
        self.entries.append(ProgressEntry(
            session_id=session_id,
            feature_id=feature.id,
            action="feature_completed",
            summary=summary
        ))

    def log_session_start(self, session_id, feature=None) -> None:
        self.entries.append(ProgressEntry(
            session_id=session_id,
            feature_id=feature.id if feature else None,
            action="session_started",
            summary="Session started"
        ))

    def initialize(self, project_name: str) -> None:
        self.initialized_project = project_name


# =============================================================================
# Tests for Protocol Compliance
# =============================================================================

class TestProtocolCompliance:
    """Tests that implementations satisfy protocol requirements."""

    def test_mock_git_satisfies_protocol(self):
        """MockGitOperations should satisfy GitOperations protocol."""
        mock = MockGitOperations()
        assert isinstance(mock, GitOperations)

    def test_mock_progress_satisfies_protocol(self):
        """MockProgressLog should satisfy ProgressLog protocol."""
        mock = MockProgressLog()
        assert isinstance(mock, ProgressLog)


# =============================================================================
# Tests for SessionRecoveryManager
# =============================================================================

class TestSessionRecoveryManager:
    """Tests for SessionRecoveryManager class."""

    def test_initialization(self, tmp_path):
        """Should initialize with correct dependencies."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)

        manager = SessionRecoveryManager(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions
        )

        assert manager.config == config
        assert manager.project_path == tmp_path
        assert not manager.is_shutdown_requested()

    def test_shutdown_flag(self, tmp_path):
        """Should track shutdown request state."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)

        manager = SessionRecoveryManager(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions
        )

        assert not manager.is_shutdown_requested()
        manager._shutdown_requested = True
        assert manager.is_shutdown_requested()

    def test_set_current_context(self, tmp_path):
        """Should track current feature and session."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)

        manager = SessionRecoveryManager(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions
        )

        feature = Feature(id="f1", name="Test Feature", description="Test")
        session = sessions.create_session()

        manager.set_current_context(feature=feature, session=session)

        assert manager._current_feature == feature
        assert manager._current_session == session

    def test_save_session_state(self, tmp_path):
        """Should save session state for recovery."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)

        manager = SessionRecoveryManager(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions
        )

        feature = Feature(id="f1", name="Test Feature", description="Test")
        session = sessions.create_session()

        manager.save_session_state(
            session=session,
            feature=feature,
            context_percent=50.0,
            handoff_notes="Continue work"
        )

        # Check state was saved
        loaded = session.load_state()
        assert loaded is not None
        assert loaded.current_feature_id == "f1"
        assert loaded.context_usage_percent == 50.0

    @pytest.mark.asyncio
    async def test_graceful_shutdown_commits_changes(self, tmp_path):
        """Should commit uncommitted changes on shutdown."""
        config = HarnessConfig()
        git = MockGitOperations(has_changes=True)
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)

        manager = SessionRecoveryManager(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions
        )

        feature = Feature(id="f1", name="Test Feature", description="Test")
        session = sessions.create_session()
        manager.set_current_context(feature=feature, session=session)

        await manager.graceful_shutdown()

        assert git.staged_called
        assert git.commit_called
        assert "shutdown" in git.last_commit_message.lower()

    @pytest.mark.asyncio
    async def test_check_for_recovery_returns_none_without_state(self, tmp_path):
        """Should return None when no recovery state exists."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)

        manager = SessionRecoveryManager(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions
        )

        result = await manager.check_for_recovery()
        assert result is None


# =============================================================================
# Tests for FeatureCompletionHandler
# =============================================================================

class TestFeatureCompletionHandler:
    """Tests for FeatureCompletionHandler class."""

    def test_initialization(self, tmp_path):
        """Should initialize with correct dependencies."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        alert_manager = Mock()
        session_history = Mock()

        handler = FeatureCompletionHandler(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            alert_manager=alert_manager,
            session_history=session_history
        )

        assert handler.config == config
        assert handler.project_path == tmp_path
        assert handler.get_total_cost() == 0.0

    @pytest.mark.asyncio
    async def test_run_tests_no_command(self, tmp_path):
        """Should pass when no test command is configured."""
        config = HarnessConfig(test_command=None)
        git = MockGitOperations()
        progress = MockProgressLog()
        alert_manager = Mock()
        session_history = Mock()

        handler = FeatureCompletionHandler(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            alert_manager=alert_manager,
            session_history=session_history
        )

        success, message = await handler.run_tests()
        assert success
        assert "No test command" in message

    def test_record_session_tracks_cost(self, tmp_path):
        """Should track cumulative cost across sessions."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        alert_manager = Mock()
        session_history = Mock()
        session_history.add_record = Mock()

        handler = FeatureCompletionHandler(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            alert_manager=alert_manager,
            session_history=session_history
        )

        # Create mock session and result
        mock_session = Mock()
        mock_session.session_id = "test-session"

        feature = Feature(id="f1", name="Test", description="Test")

        # Create result with usage stats
        from autonomous_dev_agent.models import UsageStats
        result = SessionResult(
            session_id="test-session",
            success=True,
            context_usage_percent=50.0,
            usage_stats=UsageStats(cost_usd=0.05)
        )

        handler.record_session(
            session=mock_session,
            feature=feature,
            result=result,
            outcome=SessionOutcome.SUCCESS
        )

        assert handler.get_total_cost() == 0.05

        # Record another session
        handler.record_session(
            session=mock_session,
            feature=feature,
            result=result,
            outcome=SessionOutcome.SUCCESS
        )

        assert handler.get_total_cost() == 0.10

    def test_set_backlog_saver(self, tmp_path):
        """Should allow setting the backlog saver callback."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        alert_manager = Mock()
        session_history = Mock()

        handler = FeatureCompletionHandler(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            alert_manager=alert_manager,
            session_history=session_history
        )

        saver_called = False

        def test_saver():
            nonlocal saver_called
            saver_called = True

        handler.set_backlog_saver(test_saver)
        handler._save_backlog()

        assert saver_called


# =============================================================================
# Tests for SessionOrchestrator
# =============================================================================

class TestSessionOrchestrator:
    """Tests for SessionOrchestrator class."""

    def test_initialization(self, tmp_path):
        """Should initialize with correct dependencies."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)
        workspace = Mock()
        workspace.ensure_structure = Mock()
        workspace.get_next_session_id = Mock(return_value="session-001")
        model_selector = Mock()
        alert_manager = Mock()
        session_history = Mock()

        orchestrator = SessionOrchestrator(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions,
            workspace=workspace,
            model_selector=model_selector,
            alert_manager=alert_manager,
            session_history=session_history
        )

        assert orchestrator.config == config
        assert orchestrator.project_path == tmp_path

    def test_set_handlers(self, tmp_path):
        """Should allow setting completion and recovery handlers."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)
        workspace = Mock()
        workspace.ensure_structure = Mock()
        model_selector = Mock()
        alert_manager = Mock()
        session_history = Mock()

        orchestrator = SessionOrchestrator(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions,
            workspace=workspace,
            model_selector=model_selector,
            alert_manager=alert_manager,
            session_history=session_history
        )

        completion_handler = Mock()
        recovery_manager = Mock()

        orchestrator.set_completion_handler(completion_handler)
        orchestrator.set_recovery_manager(recovery_manager)

        assert orchestrator._completion_handler == completion_handler
        assert orchestrator._recovery_manager == recovery_manager

    def test_format_acceptance_criteria(self, tmp_path):
        """Should format acceptance criteria correctly."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)
        workspace = Mock()
        model_selector = Mock()
        alert_manager = Mock()
        session_history = Mock()

        orchestrator = SessionOrchestrator(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions,
            workspace=workspace,
            model_selector=model_selector,
            alert_manager=alert_manager,
            session_history=session_history
        )

        # Feature with criteria
        feature = Feature(
            id="f1",
            name="Test",
            description="Test",
            acceptance_criteria=["Criteria 1", "Criteria 2"]
        )

        result = orchestrator._format_acceptance_criteria(feature)
        assert "- [ ] Criteria 1" in result
        assert "- [ ] Criteria 2" in result

        # Feature without criteria
        feature_no_criteria = Feature(id="f2", name="Test", description="Test")
        result_empty = orchestrator._format_acceptance_criteria(feature_no_criteria)
        assert "No specific criteria" in result_empty

    def test_calculate_retry_delay(self, tmp_path):
        """Should calculate retry delay with exponential backoff."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)
        workspace = Mock()
        model_selector = Mock()
        alert_manager = Mock()
        session_history = Mock()

        orchestrator = SessionOrchestrator(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions,
            workspace=workspace,
            model_selector=model_selector,
            alert_manager=alert_manager,
            session_history=session_history
        )

        from autonomous_dev_agent.models import RetryConfig
        retry_config = RetryConfig(
            base_delay_seconds=5.0,
            exponential_base=2.0,
            jitter_factor=0.0,  # No jitter for predictable test
            max_delay_seconds=300.0
        )

        # First attempt should be base delay
        delay_0 = orchestrator._calculate_retry_delay(0, retry_config)
        assert delay_0 == 5.0

        # Second attempt should be double
        delay_1 = orchestrator._calculate_retry_delay(1, retry_config)
        assert delay_1 == 10.0

        # Third attempt should be 4x
        delay_2 = orchestrator._calculate_retry_delay(2, retry_config)
        assert delay_2 == 20.0

    def test_should_retry_respects_max_retries(self, tmp_path):
        """Should not retry when max retries exceeded."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)
        workspace = Mock()
        model_selector = Mock()
        alert_manager = Mock()
        session_history = Mock()

        orchestrator = SessionOrchestrator(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions,
            workspace=workspace,
            model_selector=model_selector,
            alert_manager=alert_manager,
            session_history=session_history
        )

        from autonomous_dev_agent.models import RetryConfig, ErrorCategory
        retry_config = RetryConfig(max_retries=2)

        result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=0.0,
            error_category=ErrorCategory.TRANSIENT
        )

        # Should retry at attempts 0 and 1
        assert orchestrator._should_retry(result, 0, retry_config)
        assert orchestrator._should_retry(result, 1, retry_config)

        # Should not retry at attempt 2 (max reached)
        assert not orchestrator._should_retry(result, 2, retry_config)

    def test_should_retry_respects_success(self, tmp_path):
        """Should not retry successful sessions."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)
        workspace = Mock()
        model_selector = Mock()
        alert_manager = Mock()
        session_history = Mock()

        orchestrator = SessionOrchestrator(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions,
            workspace=workspace,
            model_selector=model_selector,
            alert_manager=alert_manager,
            session_history=session_history
        )

        from autonomous_dev_agent.models import RetryConfig

        retry_config = RetryConfig(max_retries=3)

        success_result = SessionResult(
            session_id="test",
            success=True,
            context_usage_percent=0.0
        )

        assert not orchestrator._should_retry(success_result, 0, retry_config)

    def test_should_retry_respects_handoff(self, tmp_path):
        """Should not retry handoff sessions."""
        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()
        sessions = SessionManager(config, tmp_path)
        workspace = Mock()
        model_selector = Mock()
        alert_manager = Mock()
        session_history = Mock()

        orchestrator = SessionOrchestrator(
            config=config,
            project_path=tmp_path,
            progress=progress,
            git=git,
            session_manager=sessions,
            workspace=workspace,
            model_selector=model_selector,
            alert_manager=alert_manager,
            session_history=session_history
        )

        from autonomous_dev_agent.models import RetryConfig

        retry_config = RetryConfig(max_retries=3)

        handoff_result = SessionResult(
            session_id="test",
            success=False,
            context_usage_percent=75.0,
            handoff_requested=True
        )

        assert not orchestrator._should_retry(handoff_result, 0, retry_config)


# =============================================================================
# Integration Tests
# =============================================================================

class TestOrchestrationIntegration:
    """Integration tests for orchestration components working together."""

    def test_harness_with_injected_components(self, tmp_path):
        """Should work with injected mock components."""
        from autonomous_dev_agent.harness import AutonomousHarness

        config = HarnessConfig()
        git = MockGitOperations()
        progress = MockProgressLog()

        harness = AutonomousHarness(
            project_path=tmp_path,
            config=config,
            git=git,
            progress=progress
        )

        assert harness.git == git
        assert harness.progress == progress

    def test_components_share_dependencies(self, tmp_path):
        """Components should share the same dependency instances."""
        from autonomous_dev_agent.harness import AutonomousHarness

        config = HarnessConfig()

        harness = AutonomousHarness(
            project_path=tmp_path,
            config=config
        )

        # All components should share the same git instance
        assert harness._orchestrator.git == harness.git
        assert harness._completion_handler.git == harness.git
        assert harness._recovery_manager.git == harness.git

        # All components should share the same progress instance
        assert harness._orchestrator.progress == harness.progress
        assert harness._completion_handler.progress == harness.progress
        assert harness._recovery_manager.progress == harness.progress
