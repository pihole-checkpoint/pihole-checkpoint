"""Service for retrieving Pi-hole credentials from environment."""

from django.conf import settings


class CredentialService:
    """Service for retrieving Pi-hole credentials."""

    @staticmethod
    def get_credentials() -> dict:
        """
        Get Pi-hole credentials from environment.

        Returns:
            dict with keys: url, password, verify_ssl

        Raises:
            ValueError if required credentials are missing
        """
        url = settings.PIHOLE_URL
        password = settings.PIHOLE_PASSWORD

        if not url:
            raise ValueError("PIHOLE_URL environment variable is required")
        if not password:
            raise ValueError("PIHOLE_PASSWORD environment variable is required")

        return {
            "url": url,
            "password": password,
            "verify_ssl": settings.PIHOLE_VERIFY_SSL,
        }

    @staticmethod
    def is_configured() -> bool:
        """Check if Pi-hole credentials are configured."""
        return bool(settings.PIHOLE_URL and settings.PIHOLE_PASSWORD)

    @staticmethod
    def get_status() -> dict:
        """
        Get the configuration status for display in UI.

        Returns:
            dict with url, has_password, verify_ssl
        """
        return {
            "url": settings.PIHOLE_URL or None,
            "has_password": bool(settings.PIHOLE_PASSWORD),
            "verify_ssl": settings.PIHOLE_VERIFY_SSL,
        }
