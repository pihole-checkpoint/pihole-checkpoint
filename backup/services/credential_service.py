"""Service for retrieving Pi-hole credentials from environment."""

import os
import re


class CredentialService:
    """Service for retrieving Pi-hole credentials.

    Credentials are read from environment variables using the pattern:
        PIHOLE_{PREFIX}_URL
        PIHOLE_{PREFIX}_PASSWORD
        PIHOLE_{PREFIX}_VERIFY_SSL
    """

    @staticmethod
    def get_credentials(env_prefix: str) -> dict:
        """
        Get Pi-hole credentials from environment for a given prefix.

        Args:
            env_prefix: The environment variable prefix (e.g., "PRIMARY")

        Returns:
            dict with keys: url, password, verify_ssl

        Raises:
            ValueError if required credentials are missing
        """
        url = os.environ.get(f"PIHOLE_{env_prefix}_URL", "")
        password = os.environ.get(f"PIHOLE_{env_prefix}_PASSWORD", "")
        verify_ssl = os.environ.get(f"PIHOLE_{env_prefix}_VERIFY_SSL", "false").lower() == "true"

        if not url:
            raise ValueError(f"PIHOLE_{env_prefix}_URL environment variable is required")
        if not password:
            raise ValueError(f"PIHOLE_{env_prefix}_PASSWORD environment variable is required")

        return {
            "url": url,
            "password": password,
            "verify_ssl": verify_ssl,
        }

    @staticmethod
    def is_configured(env_prefix: str) -> bool:
        """Check if Pi-hole credentials are configured for a given prefix."""
        return bool(os.environ.get(f"PIHOLE_{env_prefix}_URL") and os.environ.get(f"PIHOLE_{env_prefix}_PASSWORD"))

    @staticmethod
    def get_status(env_prefix: str) -> dict:
        """
        Get the configuration status for display in UI.

        Args:
            env_prefix: The environment variable prefix (e.g., "PRIMARY")

        Returns:
            dict with url, has_password, verify_ssl
        """
        return {
            "url": os.environ.get(f"PIHOLE_{env_prefix}_URL") or None,
            "has_password": bool(os.environ.get(f"PIHOLE_{env_prefix}_PASSWORD")),
            "verify_ssl": os.environ.get(f"PIHOLE_{env_prefix}_VERIFY_SSL", "false").lower() == "true",
        }

    @staticmethod
    def discover_prefixes() -> list[dict]:
        """
        Scan environment variables to discover Pi-hole instance prefixes.

        Looks for keys matching PIHOLE_{PREFIX}_URL and extracts the prefix.

        Returns:
            List of dicts with 'prefix' and 'url' keys.
        """
        pattern = re.compile(r"^PIHOLE_([A-Z][A-Z0-9_]*)_URL$")
        results = []

        for key, value in os.environ.items():
            match = pattern.match(key)
            if match and value:
                prefix = match.group(1)
                # Exclude partial matches like PIHOLE_VERIFY_SSL
                if prefix not in ("VERIFY",):
                    results.append({"prefix": prefix, "url": value})

        return results
