import logging

from django.apps import AppConfig


class BackupConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backup"
    verbose_name = "Pi-hole Checkpoint"

    def ready(self):
        """Check for required configuration on startup."""
        from django.conf import settings

        logger = logging.getLogger(__name__)

        if not settings.PIHOLE_URL or not settings.PIHOLE_PASSWORD:
            logger.warning(
                "Pi-hole credentials not configured. "
                "Set PIHOLE_URL and PIHOLE_PASSWORD environment variables to enable backups."
            )
