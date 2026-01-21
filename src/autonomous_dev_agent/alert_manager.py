"""Alert management for the autonomous dev agent.

Handles storing alerts, desktop notifications, and alert state management.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Alert, AlertType, AlertSeverity


class AlertManager:
    """Manages alerts for the dashboard.

    Stores alerts in .ada/alerts.json (new) or .ada_alerts.json (legacy)
    and provides methods for adding, reading, and dismissing alerts.
    """

    DEFAULT_FILENAME = ".ada_alerts.json"
    MAX_ALERTS = 100  # Maximum alerts to keep in storage

    def __init__(
        self,
        project_path: Path,
        filename: Optional[str] = None,
        enable_desktop_notifications: bool = True
    ):
        """Initialize alert manager.

        Args:
            project_path: Path to the project directory
            filename: Custom filename (overrides auto-detection)
            enable_desktop_notifications: Whether to show desktop notifications
        """
        self.project_path = Path(project_path)
        self.filename = filename
        self._alerts_file = self._get_alerts_file_path()
        self._alerts: list[Alert] = []
        self._desktop_notifications_enabled = enable_desktop_notifications
        self._load()

    def _get_alerts_file_path(self) -> Path:
        """Get the alerts file path with backward compatibility.

        New location: .ada/alerts.json
        Legacy location: .ada_alerts.json

        Returns new location if .ada/ exists, otherwise legacy location.
        """
        # If custom filename specified, use it directly
        if self.filename:
            return self.project_path / self.filename

        new_path = self.project_path / ".ada" / "alerts.json"
        legacy_path = self.project_path / self.DEFAULT_FILENAME

        # Check if legacy file exists first (takes precedence for backward compat)
        if legacy_path.exists():
            return legacy_path

        # If .ada/ workspace exists, use new location
        if (self.project_path / ".ada").exists():
            # .ada/ dir exists, so use it (alerts.json is at .ada/ level, no subdir needed)
            return new_path

        # Default to legacy location for projects without .ada/
        return legacy_path

    def _load(self) -> None:
        """Load alerts from disk."""
        if not self._alerts_file.exists():
            self._alerts = []
            return

        try:
            data = json.loads(self._alerts_file.read_text())
            if isinstance(data, list):
                self._alerts = [Alert.model_validate(a) for a in data]
            elif isinstance(data, dict) and "alerts" in data:
                self._alerts = [Alert.model_validate(a) for a in data["alerts"]]
            else:
                self._alerts = []
        except (json.JSONDecodeError, Exception) as e:
            print(f"[AlertManager] Warning: Could not load alerts: {e}")
            self._alerts = []

    def _save(self) -> None:
        """Save alerts to disk."""
        # Trim to max alerts before saving
        if len(self._alerts) > self.MAX_ALERTS:
            # Keep newest alerts
            self._alerts.sort(key=lambda a: a.timestamp, reverse=True)
            self._alerts = self._alerts[:self.MAX_ALERTS]

        data = [a.model_dump(mode="json") for a in self._alerts]
        self._alerts_file.write_text(json.dumps(data, indent=2, default=str))

    def _send_desktop_notification(self, title: str, message: str) -> None:
        """Send a desktop notification.

        Uses plyer for cross-platform support.
        Fails silently if plyer is not available.
        """
        if not self._desktop_notifications_enabled:
            return

        try:
            from plyer import notification
            notification.notify(
                title=f"ADA: {title}",
                message=message,
                app_name="Autonomous Dev Agent",
                timeout=10,
            )
        except ImportError:
            # plyer not installed, skip desktop notifications
            pass
        except Exception as e:
            # Any other error, just log and continue
            print(f"[AlertManager] Desktop notification failed: {e}")

    def add_alert(
        self,
        alert_type: AlertType,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.INFO,
        feature_id: Optional[str] = None,
        session_id: Optional[str] = None,
        send_notification: bool = True,
    ) -> Alert:
        """Add a new alert.

        Args:
            alert_type: Type of the alert
            title: Short title
            message: Detailed message
            severity: Alert severity level
            feature_id: Related feature ID
            session_id: Related session ID
            send_notification: Whether to send a desktop notification

        Returns:
            The created Alert
        """
        alert = Alert(
            id=str(uuid.uuid4()),
            type=alert_type,
            severity=severity,
            title=title,
            message=message,
            timestamp=datetime.now(),
            read=False,
            dismissed=False,
            feature_id=feature_id,
            session_id=session_id,
        )

        self._alerts.append(alert)
        self._save()

        # Send desktop notification for important alerts
        if send_notification and severity in (AlertSeverity.WARNING, AlertSeverity.ERROR):
            self._send_desktop_notification(title, message)

        return alert

    def get_all_alerts(self, include_dismissed: bool = False) -> list[Alert]:
        """Get all alerts.

        Args:
            include_dismissed: Whether to include dismissed alerts

        Returns:
            List of alerts, newest first
        """
        alerts = self._alerts if include_dismissed else [
            a for a in self._alerts if not a.dismissed
        ]
        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def get_unread_alerts(self) -> list[Alert]:
        """Get all unread alerts.

        Returns:
            List of unread alerts, newest first
        """
        unread = [a for a in self._alerts if not a.read and not a.dismissed]
        return sorted(unread, key=lambda a: a.timestamp, reverse=True)

    def get_unread_count(self) -> int:
        """Get count of unread alerts.

        Returns:
            Number of unread alerts
        """
        return len([a for a in self._alerts if not a.read and not a.dismissed])

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get a specific alert by ID.

        Args:
            alert_id: Alert ID to find

        Returns:
            Alert if found, None otherwise
        """
        for alert in self._alerts:
            if alert.id == alert_id:
                return alert
        return None

    def mark_read(self, alert_id: str) -> bool:
        """Mark an alert as read.

        Args:
            alert_id: Alert ID to mark read

        Returns:
            True if alert was found and marked read
        """
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.read = True
                self._save()
                return True
        return False

    def mark_all_read(self) -> int:
        """Mark all alerts as read.

        Returns:
            Number of alerts marked read
        """
        count = 0
        for alert in self._alerts:
            if not alert.read:
                alert.read = True
                count += 1
        if count > 0:
            self._save()
        return count

    def dismiss(self, alert_id: str) -> bool:
        """Dismiss an alert.

        Args:
            alert_id: Alert ID to dismiss

        Returns:
            True if alert was found and dismissed
        """
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.dismissed = True
                self._save()
                return True
        return False

    def dismiss_all(self) -> int:
        """Dismiss all alerts.

        Returns:
            Number of alerts dismissed
        """
        count = 0
        for alert in self._alerts:
            if not alert.dismissed:
                alert.dismissed = True
                count += 1
        if count > 0:
            self._save()
        return count

    def clear(self) -> None:
        """Clear all alerts from storage."""
        self._alerts = []
        self._save()

    def count(self) -> int:
        """Get total number of alerts (including dismissed)."""
        return len(self._alerts)


# Helper functions for common alert types

def create_session_failed_alert(
    manager: AlertManager,
    session_id: str,
    feature_id: Optional[str],
    error_message: str,
) -> Alert:
    """Create an alert for a failed session."""
    feature_info = f" on feature {feature_id}" if feature_id else ""
    return manager.add_alert(
        alert_type=AlertType.SESSION_FAILED,
        title="Session Failed",
        message=f"Session {session_id[:8]}{feature_info} failed: {error_message}",
        severity=AlertSeverity.ERROR,
        feature_id=feature_id,
        session_id=session_id,
    )


def create_feature_completed_alert(
    manager: AlertManager,
    feature_id: str,
    feature_name: str,
    sessions_spent: int,
) -> Alert:
    """Create an alert for a completed feature."""
    return manager.add_alert(
        alert_type=AlertType.FEATURE_COMPLETED,
        title="Feature Completed",
        message=f"'{feature_name}' completed after {sessions_spent} session(s)",
        severity=AlertSeverity.SUCCESS,
        feature_id=feature_id,
    )


def create_feature_blocked_alert(
    manager: AlertManager,
    feature_id: str,
    feature_name: str,
    reason: str,
) -> Alert:
    """Create an alert for a blocked feature."""
    return manager.add_alert(
        alert_type=AlertType.FEATURE_BLOCKED,
        title="Feature Blocked",
        message=f"'{feature_name}' is blocked: {reason}",
        severity=AlertSeverity.WARNING,
        feature_id=feature_id,
    )


def create_handoff_alert(
    manager: AlertManager,
    session_id: str,
    feature_id: Optional[str],
    context_percent: float,
) -> Alert:
    """Create an alert for a context handoff."""
    feature_info = f" on feature {feature_id}" if feature_id else ""
    return manager.add_alert(
        alert_type=AlertType.HANDOFF_OCCURRED,
        title="Context Handoff",
        message=f"Session{feature_info} handed off at {context_percent:.1f}% context",
        severity=AlertSeverity.INFO,
        feature_id=feature_id,
        session_id=session_id,
        send_notification=False,  # Handoffs are routine, no desktop notification
    )
