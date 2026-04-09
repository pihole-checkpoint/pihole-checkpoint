"""Tests for home view."""

import pytest
from django.urls import reverse

from backup.models import PiholeConfig


@pytest.mark.django_db
class TestHomeView:
    """Tests for the home view."""

    def test_returns_200_with_no_instances(self, client, auth_disabled_settings):
        """Home should return 200 with empty state when no instances exist."""
        url = reverse("home")
        response = client.get(url)
        assert response.status_code == 200

    def test_shows_empty_state_when_no_instances(self, client, auth_disabled_settings):
        """Home should show empty state message when no instances exist."""
        url = reverse("home")
        response = client.get(url)

        assert response.status_code == 200
        templates_used = [t.name for t in response.templates]
        assert "backup/home.html" in templates_used
        assert "No Pi-hole instances" in response.content.decode()

    def test_redirects_when_single_instance(self, client, pihole_config, auth_disabled_settings):
        """Home should redirect to instance dashboard when only one instance exists."""
        url = reverse("home")
        response = client.get(url)

        assert response.status_code == 302
        assert response.url == reverse("instance_dashboard", kwargs={"pk": pihole_config.pk})

    def test_shows_card_grid_with_multiple_instances(self, client, auth_disabled_settings, db):
        """Home should show card grid when multiple instances exist."""
        PiholeConfig.objects.create(env_prefix="PRIMARY", name="Primary Pi-hole")
        PiholeConfig.objects.create(env_prefix="SECONDARY", name="Secondary Pi-hole")

        url = reverse("home")
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Primary Pi-hole" in content
        assert "Secondary Pi-hole" in content

    def test_context_contains_annotated_configs(self, client, auth_disabled_settings, db):
        """Home context should contain configs with backup_count and total_size."""
        PiholeConfig.objects.create(env_prefix="PRIMARY", name="Primary Pi-hole")
        PiholeConfig.objects.create(env_prefix="SECONDARY", name="Secondary Pi-hole")

        url = reverse("home")
        response = client.get(url)

        assert "configs_with_status" in response.context
        assert len(response.context["configs_with_status"]) == 2

    def test_uses_correct_template(self, client, auth_disabled_settings, db):
        """Home should use home.html template with multiple instances."""
        PiholeConfig.objects.create(env_prefix="PRIMARY", name="Primary Pi-hole")
        PiholeConfig.objects.create(env_prefix="SECONDARY", name="Secondary Pi-hole")

        url = reverse("home")
        response = client.get(url)

        templates_used = [t.name for t in response.templates]
        assert "backup/home.html" in templates_used

    def test_requires_auth_when_enabled(self, client, auth_enabled_settings):
        """Home should require auth when REQUIRE_AUTH is True."""
        url = reverse("home")
        response = client.get(url)

        assert response.status_code == 302
        assert "login" in response.url

    def test_accessible_when_authenticated(self, authenticated_client, auth_enabled_settings):
        """Home should be accessible when authenticated."""
        url = reverse("home")
        response = authenticated_client.get(url)

        # Either 200 (empty state) or 302 (redirect if single instance)
        assert response.status_code in (200, 302)
