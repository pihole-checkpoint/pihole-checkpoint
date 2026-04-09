"""Unit tests for CredentialService."""

import pytest

from backup.services.credential_service import CredentialService


class TestCredentialServiceGetCredentials:
    """Tests for CredentialService.get_credentials()."""

    def test_returns_credentials_when_configured(self, monkeypatch):
        """get_credentials should return credentials dict when all are set."""
        monkeypatch.setenv("PIHOLE_TEST_URL", "https://test.pihole.local")
        monkeypatch.setenv("PIHOLE_TEST_PASSWORD", "testpassword")
        monkeypatch.setenv("PIHOLE_TEST_VERIFY_SSL", "true")

        creds = CredentialService.get_credentials("TEST")

        assert creds["url"] == "https://test.pihole.local"
        assert creds["password"] == "testpassword"
        assert creds["verify_ssl"] is True

    def test_raises_error_when_url_missing(self, monkeypatch):
        """get_credentials should raise ValueError when URL is missing."""
        monkeypatch.delenv("PIHOLE_TEST_URL", raising=False)
        monkeypatch.setenv("PIHOLE_TEST_PASSWORD", "testpassword")

        with pytest.raises(ValueError, match="PIHOLE_TEST_URL"):
            CredentialService.get_credentials("TEST")

    def test_raises_error_when_password_missing(self, monkeypatch):
        """get_credentials should raise ValueError when password is missing."""
        monkeypatch.setenv("PIHOLE_TEST_URL", "https://test.pihole.local")
        monkeypatch.delenv("PIHOLE_TEST_PASSWORD", raising=False)

        with pytest.raises(ValueError, match="PIHOLE_TEST_PASSWORD"):
            CredentialService.get_credentials("TEST")

    def test_returns_false_verify_ssl_by_default(self, monkeypatch):
        """get_credentials should return verify_ssl=False by default."""
        monkeypatch.setenv("PIHOLE_TEST_URL", "https://test.pihole.local")
        monkeypatch.setenv("PIHOLE_TEST_PASSWORD", "testpassword")
        monkeypatch.delenv("PIHOLE_TEST_VERIFY_SSL", raising=False)

        creds = CredentialService.get_credentials("TEST")

        assert creds["verify_ssl"] is False


class TestCredentialServiceIsConfigured:
    """Tests for CredentialService.is_configured()."""

    def test_returns_true_when_configured(self, monkeypatch):
        """is_configured should return True when URL and password are set."""
        monkeypatch.setenv("PIHOLE_TEST_URL", "https://test.pihole.local")
        monkeypatch.setenv("PIHOLE_TEST_PASSWORD", "testpassword")

        assert CredentialService.is_configured("TEST") is True

    def test_returns_false_when_url_missing(self, monkeypatch):
        """is_configured should return False when URL is missing."""
        monkeypatch.delenv("PIHOLE_TEST_URL", raising=False)
        monkeypatch.setenv("PIHOLE_TEST_PASSWORD", "testpassword")

        assert CredentialService.is_configured("TEST") is False

    def test_returns_false_when_password_missing(self, monkeypatch):
        """is_configured should return False when password is missing."""
        monkeypatch.setenv("PIHOLE_TEST_URL", "https://test.pihole.local")
        monkeypatch.delenv("PIHOLE_TEST_PASSWORD", raising=False)

        assert CredentialService.is_configured("TEST") is False

    def test_returns_false_when_both_missing(self, monkeypatch):
        """is_configured should return False when both URL and password are missing."""
        monkeypatch.delenv("PIHOLE_TEST_URL", raising=False)
        monkeypatch.delenv("PIHOLE_TEST_PASSWORD", raising=False)

        assert CredentialService.is_configured("TEST") is False


class TestCredentialServiceGetStatus:
    """Tests for CredentialService.get_status()."""

    def test_returns_status_dict(self, monkeypatch):
        """get_status should return a dict with url, has_password, verify_ssl."""
        monkeypatch.setenv("PIHOLE_TEST_URL", "https://test.pihole.local")
        monkeypatch.setenv("PIHOLE_TEST_PASSWORD", "testpassword")
        monkeypatch.setenv("PIHOLE_TEST_VERIFY_SSL", "true")

        status = CredentialService.get_status("TEST")

        assert status["url"] == "https://test.pihole.local"
        assert status["has_password"] is True
        assert status["verify_ssl"] is True

    def test_returns_none_url_when_not_set(self, monkeypatch):
        """get_status should return url=None when env var is empty."""
        monkeypatch.delenv("PIHOLE_TEST_URL", raising=False)
        monkeypatch.setenv("PIHOLE_TEST_PASSWORD", "testpassword")

        status = CredentialService.get_status("TEST")

        assert status["url"] is None

    def test_returns_false_has_password_when_not_set(self, monkeypatch):
        """get_status should return has_password=False when env var is empty."""
        monkeypatch.setenv("PIHOLE_TEST_URL", "https://test.pihole.local")
        monkeypatch.delenv("PIHOLE_TEST_PASSWORD", raising=False)

        status = CredentialService.get_status("TEST")

        assert status["has_password"] is False


class TestCredentialServiceDiscoverPrefixes:
    """Tests for CredentialService.discover_prefixes()."""

    def test_discovers_single_prefix(self, monkeypatch):
        """discover_prefixes should find a single PIHOLE_*_URL var."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://primary.local")

        prefixes = CredentialService.discover_prefixes()

        assert len(prefixes) == 1
        assert prefixes[0]["prefix"] == "PRIMARY"
        assert prefixes[0]["url"] == "https://primary.local"

    def test_discovers_multiple_prefixes(self, monkeypatch):
        """discover_prefixes should find multiple PIHOLE_*_URL vars."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://primary.local")
        monkeypatch.setenv("PIHOLE_SECONDARY_URL", "https://secondary.local")

        prefixes = CredentialService.discover_prefixes()
        prefix_names = {p["prefix"] for p in prefixes}

        assert len(prefixes) == 2
        assert "PRIMARY" in prefix_names
        assert "SECONDARY" in prefix_names

    def test_returns_empty_when_none_configured(self, monkeypatch):
        """discover_prefixes should not find PRIMARY when its env var is removed."""
        # The autouse fixture sets PRIMARY, remove it
        monkeypatch.delenv("PIHOLE_PRIMARY_URL", raising=False)

        prefixes = CredentialService.discover_prefixes()

        # PRIMARY should not be in the results
        assert all(p["prefix"] != "PRIMARY" for p in prefixes)

    def test_ignores_empty_url_values(self, monkeypatch):
        """discover_prefixes should ignore empty URL values."""
        monkeypatch.setenv("PIHOLE_EMPTY_URL", "")

        prefixes = CredentialService.discover_prefixes()
        prefix_names = {p["prefix"] for p in prefixes}

        assert "EMPTY" not in prefix_names
