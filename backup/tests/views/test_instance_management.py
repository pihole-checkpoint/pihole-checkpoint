"""Tests for instance management views (delete_instance)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import reverse

from backup.models import BackupRecord, PiholeConfig
from backup.tests.factories import BackupRecordFactory


@pytest.mark.django_db
class TestDeleteInstance:
    """Tests for the delete_instance view."""

    def test_deletes_instance_and_redirects(self, client, pihole_config, auth_disabled_settings):
        """Deleting an instance should remove it and redirect to dashboard."""
        url = reverse("delete_instance", args=[pihole_config.id])
        with patch("backup.management.commands.runapscheduler.refresh_backup_schedules"):
            response = client.post(url)

        assert response.status_code == 302
        assert response.url == reverse("dashboard")
        assert not PiholeConfig.objects.filter(id=pihole_config.id).exists()

    def test_cascade_deletes_backup_records(self, client, pihole_config, temp_backup_dir, auth_disabled_settings):
        """Deleting an instance should cascade-delete its backup records."""
        filepath = temp_backup_dir / "test.zip"
        filepath.write_bytes(b"test")
        BackupRecordFactory(config=pihole_config, file_path=str(filepath))

        url = reverse("delete_instance", args=[pihole_config.id])
        with patch("backup.management.commands.runapscheduler.refresh_backup_schedules"):
            client.post(url)

        assert BackupRecord.objects.count() == 0

    def test_deletes_backup_files_from_disk(self, client, pihole_config, temp_backup_dir, auth_disabled_settings):
        """Deleting an instance should remove backup files from disk."""
        filepath = temp_backup_dir / "test.zip"
        filepath.write_bytes(b"test")
        BackupRecordFactory(config=pihole_config, file_path=str(filepath))

        url = reverse("delete_instance", args=[pihole_config.id])
        with patch("backup.management.commands.runapscheduler.refresh_backup_schedules"):
            client.post(url)

        assert not filepath.exists()

    def test_handles_missing_backup_file(self, client, pihole_config, temp_backup_dir, auth_disabled_settings):
        """Should not error if backup file is already gone."""
        BackupRecordFactory(
            config=pihole_config,
            file_path=str(temp_backup_dir / "nonexistent.zip"),
        )

        url = reverse("delete_instance", args=[pihole_config.id])
        with patch("backup.management.commands.runapscheduler.refresh_backup_schedules"):
            response = client.post(url)

        assert response.status_code == 302
        assert not PiholeConfig.objects.filter(id=pihole_config.id).exists()

    def test_skips_file_outside_backup_dir(self, client, pihole_config, temp_backup_dir, auth_disabled_settings):
        """Should skip deletion of files outside BACKUP_DIR."""
        BackupRecordFactory(
            config=pihole_config,
            file_path="/etc/passwd",
        )

        url = reverse("delete_instance", args=[pihole_config.id])
        with patch("backup.management.commands.runapscheduler.refresh_backup_schedules"):
            response = client.post(url)

        assert response.status_code == 302
        assert Path("/etc/passwd").exists()

    def test_returns_404_for_nonexistent(self, client, auth_disabled_settings):
        """Should return 404 for nonexistent config."""
        url = reverse("delete_instance", args=[99999])
        response = client.post(url)
        assert response.status_code == 404

    def test_schedule_refresh_failure_shows_warning(self, client, pihole_config, auth_disabled_settings):
        """If schedule refresh fails, instance is still deleted with a warning."""
        url = reverse("delete_instance", args=[pihole_config.id])
        with patch(
            "backup.management.commands.runapscheduler.refresh_backup_schedules",
            side_effect=RuntimeError("scheduler error"),
        ):
            response = client.post(url)

        assert response.status_code == 302
        assert not PiholeConfig.objects.filter(id=pihole_config.id).exists()

    def test_only_allows_post(self, client, pihole_config, auth_disabled_settings):
        """Should reject GET requests."""
        url = reverse("delete_instance", args=[pihole_config.id])
        response = client.get(url)
        assert response.status_code == 405
