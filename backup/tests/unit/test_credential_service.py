"""Unit tests for CredentialService."""

import pytest

from backup.services.credential_service import CredentialService


class TestCredentialServiceGetCredentials:
    """Tests for CredentialService.get_credentials()."""

    def test_returns_credentials_when_configured(self, settings):
        """get_credentials should return credentials dict when all are set."""
        settings.PIHOLE_URL = "https://test.pihole.local"
        settings.PIHOLE_PASSWORD = "testpassword"
        settings.PIHOLE_VERIFY_SSL = True

        creds = CredentialService.get_credentials()

        assert creds["url"] == "https://test.pihole.local"
        assert creds["password"] == "testpassword"
        assert creds["verify_ssl"] is True

    def test_raises_error_when_url_missing(self, settings):
        """get_credentials should raise ValueError when URL is missing."""
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = "testpassword"

        with pytest.raises(ValueError, match="PIHOLE_URL"):
            CredentialService.get_credentials()

    def test_raises_error_when_password_missing(self, settings):
        """get_credentials should raise ValueError when password is missing."""
        settings.PIHOLE_URL = "https://test.pihole.local"
        settings.PIHOLE_PASSWORD = ""

        with pytest.raises(ValueError, match="PIHOLE_PASSWORD"):
            CredentialService.get_credentials()

    def test_returns_false_verify_ssl_by_default(self, settings):
        """get_credentials should return verify_ssl=False by default."""
        settings.PIHOLE_URL = "https://test.pihole.local"
        settings.PIHOLE_PASSWORD = "testpassword"
        settings.PIHOLE_VERIFY_SSL = False

        creds = CredentialService.get_credentials()

        assert creds["verify_ssl"] is False


class TestCredentialServiceIsConfigured:
    """Tests for CredentialService.is_configured()."""

    def test_returns_true_when_configured(self, settings):
        """is_configured should return True when URL and password are set."""
        settings.PIHOLE_URL = "https://test.pihole.local"
        settings.PIHOLE_PASSWORD = "testpassword"

        assert CredentialService.is_configured() is True

    def test_returns_false_when_url_missing(self, settings):
        """is_configured should return False when URL is missing."""
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = "testpassword"

        assert CredentialService.is_configured() is False

    def test_returns_false_when_password_missing(self, settings):
        """is_configured should return False when password is missing."""
        settings.PIHOLE_URL = "https://test.pihole.local"
        settings.PIHOLE_PASSWORD = ""

        assert CredentialService.is_configured() is False

    def test_returns_false_when_both_missing(self, settings):
        """is_configured should return False when both URL and password are missing."""
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = ""

        assert CredentialService.is_configured() is False


class TestCredentialServiceGetStatus:
    """Tests for CredentialService.get_status()."""

    def test_returns_status_dict(self, settings):
        """get_status should return a dict with url, has_password, verify_ssl."""
        settings.PIHOLE_URL = "https://test.pihole.local"
        settings.PIHOLE_PASSWORD = "testpassword"
        settings.PIHOLE_VERIFY_SSL = True

        status = CredentialService.get_status()

        assert status["url"] == "https://test.pihole.local"
        assert status["has_password"] is True
        assert status["verify_ssl"] is True

    def test_returns_none_url_when_not_set(self, settings):
        """get_status should return url=None when PIHOLE_URL is empty."""
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = "testpassword"

        status = CredentialService.get_status()

        assert status["url"] is None

    def test_returns_false_has_password_when_not_set(self, settings):
        """get_status should return has_password=False when PIHOLE_PASSWORD is empty."""
        settings.PIHOLE_URL = "https://test.pihole.local"
        settings.PIHOLE_PASSWORD = ""

        status = CredentialService.get_status()

        assert status["has_password"] is False
