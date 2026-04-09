"""Tests for instance settings view."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestInstanceSettingsViewGet:
    """Tests for instance settings view GET requests."""

    def test_returns_200(self, client, pihole_config, auth_disabled_settings):
        """Settings GET should return 200 status."""
        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        response = client.get(url)
        assert response.status_code == 200

    def test_404_for_nonexistent_instance(self, client, auth_disabled_settings):
        """Settings should return 404 for non-existent instance."""
        url = reverse("instance_settings", kwargs={"pk": 99999})
        response = client.get(url)
        assert response.status_code == 404

    def test_populates_form_with_config(self, client, pihole_config, auth_disabled_settings):
        """Settings should populate form with config data."""
        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert response.status_code == 200
        assert "form" in response.context
        assert response.context["form"].instance == pihole_config

    def test_includes_credential_status(self, client, pihole_config, auth_disabled_settings, monkeypatch):
        """Settings should include credential status from environment."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://test.pihole.local")
        monkeypatch.setenv("PIHOLE_PRIMARY_PASSWORD", "testpass")
        monkeypatch.setenv("PIHOLE_PRIMARY_VERIFY_SSL", "true")

        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert response.status_code == 200
        assert "credential_status" in response.context
        cred_status = response.context["credential_status"]
        assert cred_status["url"] == "https://test.pihole.local"
        assert cred_status["has_password"] is True
        assert cred_status["verify_ssl"] is True

    def test_credential_status_shows_not_configured(self, client, pihole_config, auth_disabled_settings, monkeypatch):
        """Settings should show credentials not configured when env vars missing."""
        monkeypatch.delenv("PIHOLE_PRIMARY_URL", raising=False)
        monkeypatch.delenv("PIHOLE_PRIMARY_PASSWORD", raising=False)

        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert response.status_code == 200
        cred_status = response.context["credential_status"]
        assert cred_status["url"] is None
        assert cred_status["has_password"] is False

    def test_requires_auth_when_enabled(self, client, pihole_config, auth_enabled_settings):
        """Settings should require auth when REQUIRE_AUTH is True."""
        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert "login" in response.url

    def test_accessible_when_authenticated(self, authenticated_client, pihole_config, auth_enabled_settings):
        """Settings should be accessible when authenticated."""
        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_uses_correct_template(self, client, pihole_config, auth_disabled_settings):
        """Settings should use settings.html template."""
        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        templates_used = [t.name for t in response.templates]
        assert "backup/settings.html" in templates_used


@pytest.mark.django_db
class TestInstanceSettingsViewPost:
    """Tests for instance settings view POST requests."""

    def test_updates_existing_config(self, client, pihole_config, auth_disabled_settings):
        """POST should update existing config."""
        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        data = {
            "name": "Updated Pi-hole",
            "env_prefix": "PRIMARY",
            "backup_frequency": "weekly",
            "backup_time": "04:00",
            "backup_day": 1,
            "max_backups": 20,
            "max_age_days": 60,
            "is_active": True,
        }
        response = client.post(url, data)

        assert response.status_code == 302
        pihole_config.refresh_from_db()
        assert pihole_config.name == "Updated Pi-hole"
        assert pihole_config.backup_frequency == "weekly"
        assert pihole_config.max_backups == 20

    def test_validation_error_shows_form_with_errors(self, client, pihole_config, auth_disabled_settings):
        """POST with validation errors should re-render form with errors."""
        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        data = {
            "name": "",  # Required field
            "backup_frequency": "daily",
            "backup_time": "03:00",
            "backup_day": 0,
            "max_backups": 10,
            "max_age_days": 30,
        }
        response = client.post(url, data)

        assert response.status_code == 200  # Re-renders form
        assert response.context["form"].errors

    def test_requires_auth_when_enabled(self, client, pihole_config, auth_enabled_settings):
        """POST should require auth when REQUIRE_AUTH is True."""
        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        data = {"name": "Test"}
        response = client.post(url, data)

        assert response.status_code == 302
        assert "login" in response.url

    def test_redirects_to_settings_on_success(self, client, pihole_config, auth_disabled_settings):
        """POST success should redirect back to instance settings."""
        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        data = {
            "name": "Test Pi-hole",
            "env_prefix": "PRIMARY",
            "backup_frequency": "daily",
            "backup_time": "03:00",
            "backup_day": 0,
            "max_backups": 10,
            "max_age_days": 30,
            "is_active": True,
        }
        response = client.post(url, data)

        assert response.status_code == 302
        assert response.url == reverse("instance_settings", kwargs={"pk": pihole_config.pk})

    def test_disables_scheduled_backups(self, client, pihole_config, auth_disabled_settings):
        """POST should allow disabling scheduled backups."""
        assert pihole_config.is_active is True

        url = reverse("instance_settings", kwargs={"pk": pihole_config.pk})
        data = {
            "name": pihole_config.name,
            "env_prefix": pihole_config.env_prefix,
            "backup_frequency": pihole_config.backup_frequency,
            "backup_time": pihole_config.backup_time.strftime("%H:%M"),
            "backup_day": pihole_config.backup_day,
            "max_backups": pihole_config.max_backups,
            "max_age_days": pihole_config.max_age_days,
            # is_active not included = False
        }
        response = client.post(url, data)

        assert response.status_code == 302
        pihole_config.refresh_from_db()
        assert pihole_config.is_active is False
