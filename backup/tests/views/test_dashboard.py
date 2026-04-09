"""Tests for instance dashboard view."""

import pytest
from django.urls import reverse

from backup.tests.factories import BackupRecordFactory


@pytest.mark.django_db
class TestInstanceDashboardView:
    """Tests for the instance dashboard view."""

    def test_returns_200(self, client, pihole_config, auth_disabled_settings):
        """Dashboard should return 200 status."""
        url = reverse("instance_dashboard", kwargs={"pk": pihole_config.pk})
        response = client.get(url)
        assert response.status_code == 200

    def test_404_for_nonexistent_instance(self, client, auth_disabled_settings):
        """Dashboard should return 404 for non-existent instance."""
        url = reverse("instance_dashboard", kwargs={"pk": 99999})
        response = client.get(url)
        assert response.status_code == 404

    def test_shows_config_info(self, client, pihole_config, auth_disabled_settings):
        """Dashboard should show config info."""
        url = reverse("instance_dashboard", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert response.status_code == 200
        assert pihole_config.name.encode() in response.content

    def test_shows_backup_history(self, client, pihole_config, temp_backup_dir, auth_disabled_settings):
        """Dashboard should show backup history."""
        for i in range(3):
            filepath = temp_backup_dir / f"backup_{i}.zip"
            filepath.write_bytes(b"test")
            BackupRecordFactory(
                config=pihole_config,
                filename=f"backup_{i}.zip",
                file_path=str(filepath),
            )

        url = reverse("instance_dashboard", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "backup_0.zip" in content or "backup" in content.lower()

    def test_requires_auth_when_enabled(self, client, pihole_config, auth_enabled_settings):
        """Dashboard should require auth when REQUIRE_AUTH is True."""
        url = reverse("instance_dashboard", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert "login" in response.url

    def test_accessible_when_authenticated(self, authenticated_client, pihole_config, auth_enabled_settings):
        """Dashboard should be accessible when authenticated."""
        url = reverse("instance_dashboard", kwargs={"pk": pihole_config.pk})
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_uses_correct_template(self, client, pihole_config, auth_disabled_settings):
        """Dashboard should use dashboard.html template."""
        url = reverse("instance_dashboard", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert response.status_code == 200
        templates_used = [t.name for t in response.templates]
        assert "backup/dashboard.html" in templates_used

    def test_context_contains_config(self, client, pihole_config, auth_disabled_settings):
        """Dashboard context should contain config."""
        url = reverse("instance_dashboard", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert "config" in response.context
        assert response.context["config"] == pihole_config

    def test_context_contains_backups(self, client, pihole_config, temp_backup_dir, auth_disabled_settings):
        """Dashboard context should contain backups queryset."""
        filepath = temp_backup_dir / "test.zip"
        filepath.write_bytes(b"test")
        BackupRecordFactory(config=pihole_config, file_path=str(filepath))

        url = reverse("instance_dashboard", kwargs={"pk": pihole_config.pk})
        response = client.get(url)

        assert "backups" in response.context
        assert response.context["backups"].count() == 1
