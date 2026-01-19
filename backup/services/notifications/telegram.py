"""Telegram notification provider."""

import logging

import requests

from .base import NotificationEvent, NotificationPayload, NotificationProvider

logger = logging.getLogger(__name__)


class TelegramProvider(NotificationProvider):
    """Telegram bot notification provider."""

    name = "telegram"
    display_name = "Telegram"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, payload: NotificationPayload) -> bool:
        """Send notification via Telegram bot."""
        icon = "\u274c" if "failed" in payload.event.value else "\u2705"
        text = f"{icon} *{payload.title}*\n\n{payload.message}\n\n"
        text += f"\U0001f4cd Pi-hole: {payload.pihole_name}\n"
        text += f"\U0001f552 Time: {payload.timestamp}"

        if payload.details:
            text += "\n\n"
            for key, value in payload.details.items():
                text += f"*{key}:* {value}\n"

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Telegram notification failed: {e}")
            return False

    def validate_config(self) -> tuple[bool, str]:
        """Validate Telegram bot configuration."""
        if not self.bot_token:
            return False, "Bot token is required"
        if not self.chat_id:
            return False, "Chat ID is required"
        return True, ""

    def test_connection(self) -> tuple[bool, str]:
        """Send a test notification to Telegram."""
        try:
            payload = NotificationPayload(
                event=NotificationEvent.BACKUP_SUCCESS,
                title="Test Notification",
                message="Pi-hole Checkpoint notifications are working!",
                pihole_name="Test",
                timestamp="Now",
            )
            if self.send(payload):
                return True, "Test notification sent successfully"
            return False, "Failed to send test notification"
        except Exception as e:
            return False, str(e)
