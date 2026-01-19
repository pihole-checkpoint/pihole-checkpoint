"""Notification service for orchestrating notifications across providers."""

import logging
from concurrent.futures import ThreadPoolExecutor

from .base import NotificationPayload, NotificationProvider
from .config import get_notification_settings
from .discord import DiscordProvider
from .homeassistant import HomeAssistantProvider
from .pushbullet import PushbulletProvider
from .slack import SlackProvider
from .telegram import TelegramProvider

logger = logging.getLogger(__name__)

PROVIDERS: dict[str, type[NotificationProvider]] = {
    "discord": DiscordProvider,
    "slack": SlackProvider,
    "telegram": TelegramProvider,
    "pushbullet": PushbulletProvider,
    "homeassistant": HomeAssistantProvider,
}


class NotificationService:
    """Manages sending notifications across multiple providers."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.settings = get_notification_settings()

    def send_notification(self, payload: NotificationPayload) -> None:
        """
        Send notification to all configured providers.
        Runs asynchronously to not block the main operation.
        """
        if not self.settings.should_notify(payload.event.value):
            logger.debug(f"Notifications disabled for event: {payload.event.value}")
            return

        for config in self.settings.providers:
            provider_name = config.get("provider")
            if provider_name not in PROVIDERS:
                logger.warning(f"Unknown notification provider: {provider_name}")
                continue

            # Submit to thread pool for async execution
            self.executor.submit(self._send_to_provider, provider_name, config, payload)

    def _send_to_provider(self, provider_name: str, config: dict, payload: NotificationPayload) -> None:
        """Send notification to a single provider."""
        try:
            provider = self._create_provider(provider_name, config)
            if provider is None:
                return

            success = provider.send(payload)
            if success:
                logger.info(f"Notification sent via {provider_name}")
            else:
                logger.warning(f"Notification to {provider_name} returned failure status")
        except Exception as e:
            logger.exception(f"Failed to send notification via {provider_name}: {e}")

    def _create_provider(self, provider_name: str, config: dict) -> NotificationProvider | None:
        """Create provider instance from config."""
        try:
            if provider_name == "discord":
                return DiscordProvider(webhook_url=config["webhook_url"])
            elif provider_name == "slack":
                return SlackProvider(webhook_url=config["webhook_url"])
            elif provider_name == "telegram":
                return TelegramProvider(bot_token=config["bot_token"], chat_id=config["chat_id"])
            elif provider_name == "pushbullet":
                return PushbulletProvider(api_key=config["api_key"])
            elif provider_name == "homeassistant":
                return HomeAssistantProvider(
                    url=config["url"],
                    token=config.get("token", ""),
                    webhook_id=config.get("webhook_id", ""),
                )
            else:
                logger.error(f"Unknown provider: {provider_name}")
                return None
        except KeyError as e:
            logger.error(f"Missing config key for {provider_name}: {e}")
            return None

    def get_enabled_providers(self) -> list[str]:
        """Get list of enabled provider display names."""
        return self.settings.get_enabled_provider_names()

    def is_enabled(self) -> bool:
        """Check if any notification providers are configured."""
        return bool(self.settings.providers)


# Singleton instance
_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    """Get notification service (cached singleton)."""
    global _service
    if _service is None:
        _service = NotificationService()
    return _service
