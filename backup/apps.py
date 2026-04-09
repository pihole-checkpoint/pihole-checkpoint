import logging

from django.apps import AppConfig


class BackupConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backup"
    verbose_name = "Pi-hole Checkpoint"

    def ready(self):
        """Check for required configuration on startup."""
        from .services.credential_service import CredentialService

        logger = logging.getLogger(__name__)

        prefixes = CredentialService.discover_prefixes()
        if not prefixes:
            logger.warning(
                "No Pi-hole instances configured. "
                "Set PIHOLE_{PREFIX}_URL and PIHOLE_{PREFIX}_PASSWORD environment variables to enable backups."
            )
