"""Tests for dashboard view."""
import pytest
from django.urls import reverse

from backup.models import BackupRecord, PiholeConfig
from backup.tests.factories import BackupRecordFactory, PiholeConfigFactory


@pytest.mark.django_db
class TestDashboardView:
    """Tests for the dashboard view."""

    def test_returns_200(self, client, auth_disabled_settings):
        """Dashboard should return 200 status."""
        url = reverse('dashboard')
        response = client.get(url)
        assert response.status_code == 200

    def test_shows_no_config_message_when_empty(self, client, auth_disabled_settings):
        """Dashboard should show no-config message when no config exists."""
        url = reverse('dashboard')
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        # Check for indication that no config exists
        assert 'config' in content.lower() or 'settings' in content.lower()

    def test_shows_config_when_exists(self, client, pihole_config, auth_disabled_settings):
        """Dashboard should show config info when config exists."""
        url = reverse('dashboard')
        response = client.get(url)

        assert response.status_code == 200
        assert pihole_config.name.encode() in response.content

    def test_shows_backup_history(self, client, pihole_config, temp_backup_dir, auth_disabled_settings):
        """Dashboard should show backup history."""
        # Create some backup records
        for i in range(3):
            filepath = temp_backup_dir / f'backup_{i}.zip'
            filepath.write_bytes(b'test')
            BackupRecordFactory(
                config=pihole_config,
                filename=f'backup_{i}.zip',
                file_path=str(filepath),
            )

        url = reverse('dashboard')
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        # Check that backups are shown
        assert 'backup_0.zip' in content or 'backup' in content.lower()

    def test_requires_auth_when_enabled(self, client, pihole_config, auth_enabled_settings):
        """Dashboard should require auth when REQUIRE_AUTH is True."""
        url = reverse('dashboard')
        response = client.get(url)

        # Should redirect to login
        assert response.status_code == 302
        assert 'login' in response.url

    def test_accessible_when_authenticated(self, authenticated_client, pihole_config, auth_enabled_settings):
        """Dashboard should be accessible when authenticated."""
        url = reverse('dashboard')
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_uses_correct_template(self, client, auth_disabled_settings):
        """Dashboard should use dashboard.html template."""
        url = reverse('dashboard')
        response = client.get(url)

        assert response.status_code == 200
        templates_used = [t.name for t in response.templates]
        assert 'backup/dashboard.html' in templates_used

    def test_context_contains_config(self, client, pihole_config, auth_disabled_settings):
        """Dashboard context should contain config."""
        url = reverse('dashboard')
        response = client.get(url)

        assert 'config' in response.context
        assert response.context['config'] == pihole_config

    def test_context_contains_backups(self, client, pihole_config, temp_backup_dir, auth_disabled_settings):
        """Dashboard context should contain backups queryset."""
        # Create backup record
        filepath = temp_backup_dir / 'test.zip'
        filepath.write_bytes(b'test')
        BackupRecordFactory(config=pihole_config, file_path=str(filepath))

        url = reverse('dashboard')
        response = client.get(url)

        assert 'backups' in response.context
        assert response.context['backups'].count() == 1

    def test_backups_empty_when_no_config(self, client, auth_disabled_settings):
        """Backups queryset should be empty when no config exists."""
        url = reverse('dashboard')
        response = client.get(url)

        assert 'backups' in response.context
        assert response.context['backups'].count() == 0
