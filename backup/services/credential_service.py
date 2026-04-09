"""Service for retrieving Pi-hole credentials from environment."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backup.models import PiholeConfig


class CredentialService:
    """Service for retrieving Pi-hole credentials."""

    @staticmethod
    def get_credentials(config: PiholeConfig) -> dict:
        """
        Get Pi-hole credentials for a specific config instance.

        Returns:
            dict with keys: url, password, verify_ssl

        Raises:
            ValueError if required credentials are missing
        """
        creds = config.get_pihole_credentials()
        prefix = config.env_prefix.upper()

        if not creds["url"]:
            raise ValueError(f"PIHOLE_{prefix}_URL environment variable is required")

        if not creds["password"]:
            raise ValueError(f"PIHOLE_{prefix}_PASSWORD environment variable is required")

        return creds

    @staticmethod
    def is_configured(config: PiholeConfig) -> bool:
        """Check if Pi-hole credentials are configured for this instance."""
        return config.is_credentials_configured()

    @staticmethod
    def get_status(config: PiholeConfig) -> dict:
        """
        Get the configuration status for display in UI.

        Returns:
            dict with url, has_password, verify_ssl, env_prefix
        """
        creds = config.get_pihole_credentials()
        return {
            "url": creds["url"] or None,
            "has_password": bool(creds["password"]),
            "verify_ssl": creds["verify_ssl"],
            "env_prefix": config.env_prefix,
        }
