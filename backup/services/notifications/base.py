"""Base classes for notification providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class NotificationEvent(Enum):
    """Types of notification events."""

    BACKUP_FAILED = "backup_failed"
    BACKUP_SUCCESS = "backup_success"
    RESTORE_FAILED = "restore_failed"
    RESTORE_SUCCESS = "restore_success"
    CONNECTION_LOST = "connection_lost"


@dataclass
class NotificationPayload:
    """Data for a notification."""

    event: NotificationEvent
    title: str
    message: str
    pihole_name: str
    timestamp: str
    details: dict | None = None


class NotificationProvider(ABC):
    """Base class for notification providers."""

    name: str = "base"
    display_name: str = "Base Provider"

    @abstractmethod
    def send(self, payload: NotificationPayload) -> bool:
        """
        Send a notification.

        Returns:
            True if sent successfully, False otherwise
        """
        pass

    @abstractmethod
    def validate_config(self) -> tuple[bool, str]:
        """
        Validate provider-specific configuration.

        Returns:
            (is_valid, error_message)
        """
        pass

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """
        Send a test notification to verify configuration.

        Returns:
            (success, message)
        """
        pass
