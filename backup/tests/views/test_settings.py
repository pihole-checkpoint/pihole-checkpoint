"""Tests for settings views."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestSettingsRedirect:
    """Tests for the legacy /settings/ redirect."""

    def test_redirects_to_instance_settings(self, client, pihole_config, auth_disabled_settings):
        """Settings should redirect to instance settings when config exists."""
        url = reverse("settings")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("instance_settings", args=[pihole_config.id])

    def test_redirects_to_dashboard_when_no_config(self, client, auth_disabled_settings):
        """Settings should redirect to dashboard when no config exists."""
        url = reverse("settings")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("dashboard")


@pytest.mark.django_db
class TestInstanceSettingsGet:
    """Tests for instance settings view (read-only)."""

    def test_returns_200(self, client, pihole_config, auth_disabled_settings):
        """Instance settings GET should return 200 status."""
        url = reverse("instance_settings", args=[pihole_config.id])
        response = client.get(url)
        assert response.status_code == 200

    def test_returns_404_for_nonexistent(self, client, auth_disabled_settings):
        """Instance settings should return 404 for nonexistent config."""
        url = reverse("instance_settings", args=[99999])
        response = client.get(url)
        assert response.status_code == 404

    def test_includes_credential_status(self, client, pihole_config, auth_disabled_settings):
        """Instance settings should include credential status from environment."""
        url = reverse("instance_settings", args=[pihole_config.id])
        response = client.get(url)

        assert response.status_code == 200
        assert "credential_status" in response.context
        cred_status = response.context["credential_status"]
        assert cred_status["url"] == "https://pihole.local"
        assert cred_status["has_password"] is True
        assert cred_status["env_prefix"] == "PRIMARY"

    def test_includes_config(self, client, pihole_config, auth_disabled_settings):
        """Instance settings should include the config object."""
        url = reverse("instance_settings", args=[pihole_config.id])
        response = client.get(url)

        assert response.status_code == 200
        assert response.context["config"] == pihole_config

    def test_requires_auth_when_enabled(self, client, pihole_config, auth_enabled_settings):
        """Instance settings should require auth when REQUIRE_AUTH is True."""
        url = reverse("instance_settings", args=[pihole_config.id])
        response = client.get(url)

        assert response.status_code == 302
        assert "login" in response.url

    def test_accessible_when_authenticated(self, authenticated_client, pihole_config, auth_enabled_settings):
        """Instance settings should be accessible when authenticated."""
        url = reverse("instance_settings", args=[pihole_config.id])
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_uses_correct_template(self, client, pihole_config, auth_disabled_settings):
        """Instance settings should use settings.html template."""
        url = reverse("instance_settings", args=[pihole_config.id])
        response = client.get(url)

        templates_used = [t.name for t in response.templates]
        assert "backup/settings.html" in templates_used
