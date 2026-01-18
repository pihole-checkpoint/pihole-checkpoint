"""Integration tests for backup workflow."""
import hashlib
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from backup.models import BackupRecord, PiholeConfig
from backup.services.backup_service import BackupService
from backup.services.retention_service import RetentionService
from backup.tests.factories import BackupRecordFactory, PiholeConfigFactory


@pytest.mark.django_db
@pytest.mark.integration
class TestCompleteBackupWorkflow:
    """Integration tests for complete backup workflow."""

    def test_complete_backup_workflow(self, pihole_config, temp_backup_dir, sample_backup_data):
        """Test complete workflow: API -> file -> DB record -> config update."""
        assert pihole_config.last_successful_backup is None
        assert BackupRecord.objects.count() == 0

        with patch('backup.services.backup_service.PiholeV6Client') as mock_client_class:
            # Mock the Pi-hole client
            mock_client = MagicMock()
            mock_client.download_teleporter_backup.return_value = sample_backup_data
            mock_client_class.return_value = mock_client

            # Create backup
            service = BackupService(pihole_config)
            record = service.create_backup(is_manual=True)

        # Verify record created correctly
        assert record.status == 'success'
        assert record.is_manual is True
        assert record.config == pihole_config

        # Verify file saved to disk
        filepath = Path(record.file_path)
        assert filepath.exists()
        assert filepath.read_bytes() == sample_backup_data

        # Verify checksum calculated correctly
        expected_checksum = hashlib.sha256(sample_backup_data).hexdigest()
        assert record.checksum == expected_checksum

        # Verify file size recorded
        assert record.file_size == len(sample_backup_data)

        # Verify config updated
        pihole_config.refresh_from_db()
        assert pihole_config.last_successful_backup is not None
        assert pihole_config.last_backup_error == ''

    def test_backup_then_retention_workflow(self, temp_backup_dir, sample_backup_data):
        """Test backup creation followed by retention cleanup."""
        config = PiholeConfigFactory(max_backups=2, max_age_days=0)

        with patch('backup.services.backup_service.PiholeV6Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.download_teleporter_backup.return_value = sample_backup_data
            mock_client_class.return_value = mock_client

            # Create 5 backups
            backup_service = BackupService(config)
            for _ in range(5):
                backup_service.create_backup()

        # Should have 5 backups
        assert BackupRecord.objects.filter(config=config, status='success').count() == 5

        # Run retention
        retention_service = RetentionService()
        deleted = retention_service.enforce_retention(config)

        # Should have deleted 3 backups (5 - 2 max)
        assert deleted == 3
        remaining = BackupRecord.objects.filter(config=config, status='success')
        assert remaining.count() == 2

        # Verify files deleted
        for record in remaining:
            assert Path(record.file_path).exists()

    def test_backup_failure_recovery_workflow(self, pihole_config, temp_backup_dir, sample_backup_data):
        """Test backup failure followed by successful retry."""
        # First backup fails
        with patch('backup.services.backup_service.PiholeV6Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.download_teleporter_backup.side_effect = ConnectionError('Network error')
            mock_client_class.return_value = mock_client

            service = BackupService(pihole_config)

            with pytest.raises(ConnectionError):
                service.create_backup()

        # Verify failed record created
        failed_record = BackupRecord.objects.filter(
            config=pihole_config,
            status='failed'
        ).first()
        assert failed_record is not None
        assert 'Network error' in failed_record.error_message

        # Verify config error updated
        pihole_config.refresh_from_db()
        assert 'Network error' in pihole_config.last_backup_error
        assert pihole_config.last_successful_backup is None

        # Second backup succeeds
        with patch('backup.services.backup_service.PiholeV6Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.download_teleporter_backup.return_value = sample_backup_data
            mock_client_class.return_value = mock_client

            service = BackupService(pihole_config)
            success_record = service.create_backup()

        # Verify success
        assert success_record.status == 'success'
        pihole_config.refresh_from_db()
        assert pihole_config.last_successful_backup is not None
        assert pihole_config.last_backup_error == ''

    def test_delete_removes_file_and_record(self, pihole_config, temp_backup_dir, sample_backup_data):
        """Test that delete removes both file and database record."""
        with patch('backup.services.backup_service.PiholeV6Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.download_teleporter_backup.return_value = sample_backup_data
            mock_client_class.return_value = mock_client

            service = BackupService(pihole_config)
            record = service.create_backup()

        record_id = record.id
        filepath = Path(record.file_path)

        # Verify file exists
        assert filepath.exists()
        assert BackupRecord.objects.filter(id=record_id).exists()

        # Delete backup
        service.delete_backup(record)

        # Verify both removed
        assert not filepath.exists()
        assert not BackupRecord.objects.filter(id=record_id).exists()


@pytest.mark.django_db
@pytest.mark.integration
class TestMultiConfigWorkflow:
    """Integration tests for multi-config scenarios."""

    def test_retention_processes_multiple_configs(self, temp_backup_dir, sample_backup_data):
        """Test retention service processes multiple configs independently."""
        config1 = PiholeConfigFactory(name='Config 1', max_backups=2)
        config2 = PiholeConfigFactory(name='Config 2', max_backups=3)

        with patch('backup.services.backup_service.PiholeV6Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.download_teleporter_backup.return_value = sample_backup_data
            mock_client_class.return_value = mock_client

            # Create 5 backups for config1
            service1 = BackupService(config1)
            for _ in range(5):
                service1.create_backup()

            # Create 5 backups for config2
            service2 = BackupService(config2)
            for _ in range(5):
                service2.create_backup()

        # Run retention for all
        retention_service = RetentionService()
        total_deleted = retention_service.enforce_all()

        # Config1: 5 - 2 = 3 deleted
        # Config2: 5 - 3 = 2 deleted
        assert total_deleted == 5

        assert BackupRecord.objects.filter(config=config1, status='success').count() == 2
        assert BackupRecord.objects.filter(config=config2, status='success').count() == 3

    def test_backup_failure_doesnt_affect_other_configs(self, temp_backup_dir, sample_backup_data):
        """Test that one config's failure doesn't affect other configs."""
        config1 = PiholeConfigFactory(name='Working')
        config2 = PiholeConfigFactory(name='Broken')

        # Config1 succeeds
        with patch('backup.services.backup_service.PiholeV6Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.download_teleporter_backup.return_value = sample_backup_data
            mock_client_class.return_value = mock_client

            service1 = BackupService(config1)
            record1 = service1.create_backup()

        assert record1.status == 'success'

        # Config2 fails
        with patch('backup.services.backup_service.PiholeV6Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.download_teleporter_backup.side_effect = ConnectionError()
            mock_client_class.return_value = mock_client

            service2 = BackupService(config2)

            with pytest.raises(ConnectionError):
                service2.create_backup()

        # Config1 should still have its successful backup
        assert BackupRecord.objects.filter(config=config1, status='success').count() == 1

        # Config2 should have a failed record
        assert BackupRecord.objects.filter(config=config2, status='failed').count() == 1


@pytest.mark.django_db
@pytest.mark.integration
class TestRetentionEdgeCases:
    """Integration tests for retention edge cases."""

    def test_retention_with_mixed_success_and_failed(self, temp_backup_dir, sample_backup_data):
        """Test retention handles mixed success and failed backups correctly."""
        config = PiholeConfigFactory(max_backups=2, max_age_days=0)

        with patch('backup.services.backup_service.PiholeV6Client') as mock_client_class:
            mock_client = MagicMock()
            mock_client.download_teleporter_backup.return_value = sample_backup_data
            mock_client_class.return_value = mock_client

            service = BackupService(config)

            # Create 3 successful backups
            for _ in range(3):
                service.create_backup()

        # Create 2 failed backup records (simulating past failures)
        from backup.tests.factories import FailedBackupRecordFactory
        FailedBackupRecordFactory(config=config)
        FailedBackupRecordFactory(config=config)

        # Verify initial state
        assert BackupRecord.objects.filter(config=config, status='success').count() == 3
        assert BackupRecord.objects.filter(config=config, status='failed').count() == 2

        # Run retention
        retention_service = RetentionService()
        deleted = retention_service.enforce_retention(config)

        # Should delete 1 successful backup (3 - 2 max)
        # Failed backups aren't counted in max_backups
        assert deleted == 1
        assert BackupRecord.objects.filter(config=config, status='success').count() == 2
        # Recent failed backups should remain (less than 7 days old)
        assert BackupRecord.objects.filter(config=config, status='failed').count() == 2

    def test_retention_cleans_old_failed_records(self, temp_backup_dir):
        """Test that old failed records (>7 days) are cleaned up."""
        config = PiholeConfigFactory(max_backups=10, max_age_days=0)

        # Create old failed backup records
        from backup.tests.factories import FailedBackupRecordFactory
        old_failed1 = FailedBackupRecordFactory(config=config)
        old_failed2 = FailedBackupRecordFactory(config=config)

        # Make them old
        old_time = timezone.now() - timedelta(days=10)
        BackupRecord.objects.filter(pk__in=[old_failed1.pk, old_failed2.pk]).update(
            created_at=old_time
        )

        # Create a recent failed backup
        recent_failed = FailedBackupRecordFactory(config=config)

        # Run retention
        retention_service = RetentionService()
        retention_service.enforce_retention(config)

        # Old failed should be deleted, recent should remain
        assert not BackupRecord.objects.filter(pk=old_failed1.pk).exists()
        assert not BackupRecord.objects.filter(pk=old_failed2.pk).exists()
        assert BackupRecord.objects.filter(pk=recent_failed.pk).exists()
