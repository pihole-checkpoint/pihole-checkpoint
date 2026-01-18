"""Tests for settings view."""
import pytest
from django.urls import reverse

from backup.models import PiholeConfig
from backup.tests.factories import PiholeConfigFactory


@pytest.mark.django_db
class TestSettingsViewGet:
    """Tests for settings view GET requests."""

    def test_returns_200(self, client, auth_disabled_settings):
        """Settings GET should return 200 status."""
        url = reverse('settings')
        response = client.get(url)
        assert response.status_code == 200

    def test_shows_empty_form_when_no_config(self, client, auth_disabled_settings):
        """Settings should show empty form when no config exists."""
        url = reverse('settings')
        response = client.get(url)

        assert response.status_code == 200
        assert 'form' in response.context
        # Form should not have an instance
        assert response.context['form'].instance.pk is None

    def test_populates_form_when_config_exists(self, client, pihole_config, auth_disabled_settings):
        """Settings should populate form when config exists."""
        url = reverse('settings')
        response = client.get(url)

        assert response.status_code == 200
        assert 'form' in response.context
        assert response.context['form'].instance == pihole_config

    def test_requires_auth_when_enabled(self, client, auth_enabled_settings):
        """Settings should require auth when REQUIRE_AUTH is True."""
        url = reverse('settings')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_accessible_when_authenticated(self, authenticated_client, auth_enabled_settings):
        """Settings should be accessible when authenticated."""
        url = reverse('settings')
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_uses_correct_template(self, client, auth_disabled_settings):
        """Settings should use settings.html template."""
        url = reverse('settings')
        response = client.get(url)

        templates_used = [t.name for t in response.templates]
        assert 'backup/settings.html' in templates_used


@pytest.mark.django_db
class TestSettingsViewPost:
    """Tests for settings view POST requests."""

    def test_creates_new_config(self, client, auth_disabled_settings):
        """POST should create new config when none exists."""
        assert PiholeConfig.objects.count() == 0

        url = reverse('settings')
        data = {
            'name': 'New Pi-hole',
            'pihole_url': 'https://pihole.local',
            'password': 'testpassword',
            'verify_ssl': False,
            'backup_frequency': 'daily',
            'backup_time': '03:00',
            'backup_day': 0,
            'max_backups': 10,
            'max_age_days': 30,
            'is_active': True,
        }
        response = client.post(url, data)

        assert response.status_code == 302  # Redirect on success
        assert PiholeConfig.objects.count() == 1
        config = PiholeConfig.objects.first()
        assert config.name == 'New Pi-hole'
        assert config.pihole_url == 'https://pihole.local'

    def test_updates_existing_config(self, client, pihole_config, auth_disabled_settings):
        """POST should update existing config."""
        url = reverse('settings')
        data = {
            'name': 'Updated Pi-hole',
            'pihole_url': 'https://new-pihole.local',
            'password': '',  # Keep existing
            'verify_ssl': True,
            'backup_frequency': 'weekly',
            'backup_time': '04:00',
            'backup_day': 1,
            'max_backups': 20,
            'max_age_days': 60,
            'is_active': True,
        }
        response = client.post(url, data)

        assert response.status_code == 302
        pihole_config.refresh_from_db()
        assert pihole_config.name == 'Updated Pi-hole'
        assert pihole_config.pihole_url == 'https://new-pihole.local'
        assert pihole_config.backup_frequency == 'weekly'

    def test_validation_error_shows_form_with_errors(self, client, auth_disabled_settings):
        """POST with validation errors should re-render form with errors."""
        url = reverse('settings')
        data = {
            'name': '',  # Required field
            'pihole_url': 'not-a-url',  # Invalid URL
            'password': '',
            'backup_frequency': 'daily',
            'backup_time': '03:00',
            'backup_day': 0,
            'max_backups': 10,
            'max_age_days': 30,
        }
        response = client.post(url, data)

        assert response.status_code == 200  # Re-renders form
        assert response.context['form'].errors

    def test_requires_auth_when_enabled(self, client, auth_enabled_settings):
        """POST should require auth when REQUIRE_AUTH is True."""
        url = reverse('settings')
        data = {'name': 'Test'}
        response = client.post(url, data)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_preserves_password_when_blank(self, client, pihole_config, auth_disabled_settings):
        """POST with blank password should preserve existing password."""
        original_password = pihole_config.password

        url = reverse('settings')
        data = {
            'name': pihole_config.name,
            'pihole_url': pihole_config.pihole_url,
            'password': '',  # Blank password
            'verify_ssl': pihole_config.verify_ssl,
            'backup_frequency': pihole_config.backup_frequency,
            'backup_time': pihole_config.backup_time.strftime('%H:%M'),
            'backup_day': pihole_config.backup_day,
            'max_backups': pihole_config.max_backups,
            'max_age_days': pihole_config.max_age_days,
            'is_active': pihole_config.is_active,
        }
        response = client.post(url, data)

        assert response.status_code == 302
        pihole_config.refresh_from_db()
        assert pihole_config.password == original_password

    def test_updates_password_when_provided(self, client, pihole_config, auth_disabled_settings):
        """POST with new password should update the password."""
        url = reverse('settings')
        data = {
            'name': pihole_config.name,
            'pihole_url': pihole_config.pihole_url,
            'password': 'new-password-123',
            'verify_ssl': pihole_config.verify_ssl,
            'backup_frequency': pihole_config.backup_frequency,
            'backup_time': pihole_config.backup_time.strftime('%H:%M'),
            'backup_day': pihole_config.backup_day,
            'max_backups': pihole_config.max_backups,
            'max_age_days': pihole_config.max_age_days,
            'is_active': pihole_config.is_active,
        }
        response = client.post(url, data)

        assert response.status_code == 302
        pihole_config.refresh_from_db()
        assert pihole_config.password == 'new-password-123'

    def test_redirects_to_settings_on_success(self, client, auth_disabled_settings):
        """POST success should redirect back to settings."""
        url = reverse('settings')
        data = {
            'name': 'Test Pi-hole',
            'pihole_url': 'https://pihole.local',
            'password': 'testpassword',
            'verify_ssl': False,
            'backup_frequency': 'daily',
            'backup_time': '03:00',
            'backup_day': 0,
            'max_backups': 10,
            'max_age_days': 30,
            'is_active': True,
        }
        response = client.post(url, data)

        assert response.status_code == 302
        assert response.url == reverse('settings')
