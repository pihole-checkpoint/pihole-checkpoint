"""Unit tests for CredentialService."""

import pytest

from backup.models import PiholeConfig
from backup.services.credential_service import CredentialService


@pytest.mark.django_db
class TestCredentialServiceGetCredentials:
    """Tests for CredentialService.get_credentials()."""

    def test_returns_credentials_with_prefix(self, pihole_config, monkeypatch):
        """get_credentials should return credentials from prefix env vars."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://test.pihole.local")
        monkeypatch.setenv("PIHOLE_PRIMARY_PASSWORD", "testpassword")
        monkeypatch.setenv("PIHOLE_PRIMARY_VERIFY_SSL", "true")

        creds = CredentialService.get_credentials(pihole_config)

        assert creds["url"] == "https://test.pihole.local"
        assert creds["password"] == "testpassword"
        assert creds["verify_ssl"] is True

    def test_returns_credentials_with_legacy_fallback(self, db, settings):
        """get_credentials should fall back to legacy settings when no prefix."""
        config = PiholeConfig.objects.create(name="Legacy", env_prefix="")
        settings.PIHOLE_URL = "https://legacy.pihole.local"
        settings.PIHOLE_PASSWORD = "legacypass"
        settings.PIHOLE_VERIFY_SSL = True

        creds = CredentialService.get_credentials(config)

        assert creds["url"] == "https://legacy.pihole.local"
        assert creds["password"] == "legacypass"
        assert creds["verify_ssl"] is True

    def test_raises_error_when_url_missing(self, pihole_config, monkeypatch, settings):
        """get_credentials should raise ValueError when URL is missing from both prefixed and legacy."""
        monkeypatch.delenv("PIHOLE_PRIMARY_URL", raising=False)
        monkeypatch.setenv("PIHOLE_PRIMARY_PASSWORD", "testpassword")
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = ""

        with pytest.raises(ValueError, match="PIHOLE_PRIMARY_URL"):
            CredentialService.get_credentials(pihole_config)

    def test_raises_error_when_password_missing(self, pihole_config, monkeypatch, settings):
        """get_credentials should raise ValueError when password is missing from both prefixed and legacy."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://test.pihole.local")
        monkeypatch.delenv("PIHOLE_PRIMARY_PASSWORD", raising=False)
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = ""

        with pytest.raises(ValueError, match="PIHOLE_PRIMARY_PASSWORD"):
            CredentialService.get_credentials(pihole_config)

    def test_returns_false_verify_ssl_by_default(self, pihole_config, monkeypatch):
        """get_credentials should return verify_ssl=False by default."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://test.pihole.local")
        monkeypatch.setenv("PIHOLE_PRIMARY_PASSWORD", "testpassword")
        monkeypatch.delenv("PIHOLE_PRIMARY_VERIFY_SSL", raising=False)

        creds = CredentialService.get_credentials(pihole_config)

        assert creds["verify_ssl"] is False

    def test_raises_error_for_legacy_missing_url(self, db, settings):
        """get_credentials should raise for legacy config with missing URL."""
        config = PiholeConfig.objects.create(name="Legacy", env_prefix="")
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = "testpassword"

        with pytest.raises(ValueError, match="PIHOLE_URL"):
            CredentialService.get_credentials(config)


@pytest.mark.django_db
class TestCredentialServiceIsConfigured:
    """Tests for CredentialService.is_configured()."""

    def test_returns_true_when_configured(self, pihole_config):
        """is_configured should return True when URL and password are set."""
        assert CredentialService.is_configured(pihole_config) is True

    def test_returns_false_when_url_missing(self, pihole_config, monkeypatch, settings):
        """is_configured should return False when URL is missing from both prefixed and legacy."""
        monkeypatch.delenv("PIHOLE_PRIMARY_URL", raising=False)
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = ""

        assert CredentialService.is_configured(pihole_config) is False

    def test_returns_false_when_password_missing(self, pihole_config, monkeypatch, settings):
        """is_configured should return False when password is missing from both prefixed and legacy."""
        monkeypatch.delenv("PIHOLE_PRIMARY_PASSWORD", raising=False)
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = ""

        assert CredentialService.is_configured(pihole_config) is False

    def test_returns_false_when_both_missing(self, pihole_config, monkeypatch, settings):
        """is_configured should return False when both are missing from prefixed and legacy."""
        monkeypatch.delenv("PIHOLE_PRIMARY_URL", raising=False)
        monkeypatch.delenv("PIHOLE_PRIMARY_PASSWORD", raising=False)
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = ""

        assert CredentialService.is_configured(pihole_config) is False


@pytest.mark.django_db
class TestCredentialServiceGetStatus:
    """Tests for CredentialService.get_status()."""

    def test_returns_status_dict(self, pihole_config, monkeypatch):
        """get_status should return a dict with url, has_password, verify_ssl, env_prefix."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://test.pihole.local")
        monkeypatch.setenv("PIHOLE_PRIMARY_PASSWORD", "testpassword")
        monkeypatch.setenv("PIHOLE_PRIMARY_VERIFY_SSL", "true")

        status = CredentialService.get_status(pihole_config)

        assert status["url"] == "https://test.pihole.local"
        assert status["has_password"] is True
        assert status["verify_ssl"] is True
        assert status["env_prefix"] == "PRIMARY"

    def test_returns_none_url_when_not_set(self, pihole_config, monkeypatch, settings):
        """get_status should return url=None when env var is not set (prefixed or legacy)."""
        monkeypatch.delenv("PIHOLE_PRIMARY_URL", raising=False)
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = ""

        status = CredentialService.get_status(pihole_config)

        assert status["url"] is None

    def test_returns_false_has_password_when_not_set(self, pihole_config, monkeypatch, settings):
        """get_status should return has_password=False when password is not set (prefixed or legacy)."""
        monkeypatch.delenv("PIHOLE_PRIMARY_PASSWORD", raising=False)
        settings.PIHOLE_URL = ""
        settings.PIHOLE_PASSWORD = ""

        status = CredentialService.get_status(pihole_config)

        assert status["has_password"] is False
