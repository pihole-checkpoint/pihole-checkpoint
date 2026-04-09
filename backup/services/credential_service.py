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

        if not creds["url"]:
            if config.env_prefix:
                raise ValueError(f"PIHOLE_{config.env_prefix.upper()}_URL environment variable is required")
            raise ValueError("PIHOLE_URL environment variable is required")

        if not creds["password"]:
            if config.env_prefix:
                raise ValueError(f"PIHOLE_{config.env_prefix.upper()}_PASSWORD environment variable is required")
            raise ValueError("PIHOLE_PASSWORD environment variable is required")

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
