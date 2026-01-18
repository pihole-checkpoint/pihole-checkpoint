"""Unit tests for RetentionService."""
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.utils import timezone
from freezegun import freeze_time

from backup.models import BackupRecord, PiholeConfig
from backup.services.retention_service import RetentionService
from backup.tests.factories import (
    BackupRecordFactory,
    FailedBackupRecordFactory,
    PiholeConfigFactory,
    InactivePiholeConfigFactory,
)


@pytest.mark.django_db
class TestRetentionServiceEnforceRetention:
    """Tests for RetentionService.enforce_retention()."""

    def test_deletes_excess_by_count_keeps_newest(self, temp_backup_dir):
        """Should delete oldest backups when exceeding max_backups count."""
        config = PiholeConfigFactory(max_backups=3, max_age_days=0)

        # Create 5 backups (2 more than max)
        records = []
        for i in range(5):
            filepath = temp_backup_dir / f'backup_{i}.zip'
            filepath.write_bytes(b'test data')
            record = BackupRecordFactory(
                config=config,
                filename=f'backup_{i}.zip',
                file_path=str(filepath),
            )
            records.append(record)

        service = RetentionService()
        deleted_count = service.enforce_retention(config)

        assert deleted_count == 2
        # Should keep 3 newest
        remaining = BackupRecord.objects.filter(config=config, status='success')
        assert remaining.count() == 3

    def test_deletes_by_age(self, temp_backup_dir):
        """Should delete backups older than max_age_days."""
        config = PiholeConfigFactory(max_backups=0, max_age_days=30)  # 0 means no count limit

        # Create a recent backup
        recent_file = temp_backup_dir / 'recent.zip'
        recent_file.write_bytes(b'test data')
        recent = BackupRecordFactory(
            config=config,
            filename='recent.zip',
            file_path=str(recent_file),
        )

        # Create an old backup (40 days old)
        old_file = temp_backup_dir / 'old.zip'
        old_file.write_bytes(b'test data')
        old = BackupRecordFactory(
            config=config,
            filename='old.zip',
            file_path=str(old_file),
        )
        # Manually update created_at to be old
        old_time = timezone.now() - timedelta(days=40)
        BackupRecord.objects.filter(pk=old.pk).update(created_at=old_time)

        service = RetentionService()
        deleted_count = service.enforce_retention(config)

        assert deleted_count == 1
        assert BackupRecord.objects.filter(pk=recent.pk).exists()
        assert not BackupRecord.objects.filter(pk=old.pk).exists()
        assert not old_file.exists()

    def test_combines_count_and_age_policies(self, temp_backup_dir):
        """Should apply both count and age retention policies."""
        config = PiholeConfigFactory(max_backups=5, max_age_days=10)

        # Create 7 backups - 3 will be deleted by count policy first
        records = []
        for i in range(7):
            filepath = temp_backup_dir / f'backup_{i}.zip'
            filepath.write_bytes(b'test data')
            record = BackupRecordFactory(
                config=config,
                filename=f'backup_{i}.zip',
                file_path=str(filepath),
            )
            records.append(record)

        # Make 2 of the remaining 5 old (will be deleted by age policy)
        for record in records[:2]:
            old_time = timezone.now() - timedelta(days=15)
            BackupRecord.objects.filter(pk=record.pk).update(created_at=old_time)

        service = RetentionService()
        deleted_count = service.enforce_retention(config)

        # 2 deleted by count (7 -> 5), then 2 deleted by age
        assert deleted_count == 4
        remaining = BackupRecord.objects.filter(config=config, status='success')
        assert remaining.count() == 3

    def test_cleans_old_failed_backups(self, temp_backup_dir):
        """Should clean up failed backup records older than 7 days."""
        config = PiholeConfigFactory(max_backups=10, max_age_days=30)

        # Create a recent failed backup
        recent_failed = FailedBackupRecordFactory(config=config)

        # Create an old failed backup (10 days old)
        old_failed = FailedBackupRecordFactory(config=config)
        old_time = timezone.now() - timedelta(days=10)
        BackupRecord.objects.filter(pk=old_failed.pk).update(created_at=old_time)

        service = RetentionService()
        service.enforce_retention(config)

        # Recent failed should remain, old failed should be deleted
        assert BackupRecord.objects.filter(pk=recent_failed.pk).exists()
        assert not BackupRecord.objects.filter(pk=old_failed.pk).exists()

    def test_returns_deletion_count(self, temp_backup_dir):
        """Should return the number of deleted backups."""
        config = PiholeConfigFactory(max_backups=2, max_age_days=0)

        # Create 5 backups
        for i in range(5):
            filepath = temp_backup_dir / f'backup_{i}.zip'
            filepath.write_bytes(b'test data')
            BackupRecordFactory(
                config=config,
                filename=f'backup_{i}.zip',
                file_path=str(filepath),
            )

        service = RetentionService()
        deleted_count = service.enforce_retention(config)

        assert deleted_count == 3

    def test_handles_missing_files_gracefully(self, temp_backup_dir):
        """Should handle missing files gracefully during deletion."""
        config = PiholeConfigFactory(max_backups=1, max_age_days=0)

        # Create backups with non-existent file paths
        BackupRecordFactory(
            config=config,
            filename='exists.zip',
            file_path=str(temp_backup_dir / 'exists.zip'),
        )
        (temp_backup_dir / 'exists.zip').write_bytes(b'test')

        BackupRecordFactory(
            config=config,
            filename='missing.zip',
            file_path='/nonexistent/path/missing.zip',
        )

        service = RetentionService()
        # Should not raise exception
        deleted_count = service.enforce_retention(config)

        assert deleted_count == 1

    def test_zero_max_backups_skips_count_policy(self, temp_backup_dir):
        """max_backups=0 should skip count-based retention."""
        config = PiholeConfigFactory(max_backups=0, max_age_days=0)

        # Create many backups
        for i in range(10):
            filepath = temp_backup_dir / f'backup_{i}.zip'
            filepath.write_bytes(b'test data')
            BackupRecordFactory(
                config=config,
                filename=f'backup_{i}.zip',
                file_path=str(filepath),
            )

        service = RetentionService()
        deleted_count = service.enforce_retention(config)

        # No count-based or age-based deletion
        assert deleted_count == 0
        remaining = BackupRecord.objects.filter(config=config, status='success')
        assert remaining.count() == 10


@pytest.mark.django_db
class TestRetentionServiceEnforceAll:
    """Tests for RetentionService.enforce_all()."""

    def test_processes_all_active_configs(self, temp_backup_dir):
        """Should process all active configs."""
        config1 = PiholeConfigFactory(max_backups=1, max_age_days=0)
        config2 = PiholeConfigFactory(max_backups=1, max_age_days=0)

        # Create 3 backups for each config
        for config in [config1, config2]:
            for i in range(3):
                filepath = temp_backup_dir / f'{config.name}_{i}.zip'
                filepath.write_bytes(b'test data')
                BackupRecordFactory(
                    config=config,
                    filename=f'{config.name}_{i}.zip',
                    file_path=str(filepath),
                )

        service = RetentionService()
        total_deleted = service.enforce_all()

        # Each config should have 2 deleted (3 - 1 max)
        assert total_deleted == 4

    def test_skips_inactive_configs(self, temp_backup_dir):
        """Should skip inactive configs."""
        active = PiholeConfigFactory(max_backups=1, max_age_days=0, is_active=True)
        inactive = InactivePiholeConfigFactory(max_backups=1, max_age_days=0)

        # Create 3 backups for each
        for config in [active, inactive]:
            for i in range(3):
                filepath = temp_backup_dir / f'{config.name}_{i}.zip'
                filepath.write_bytes(b'test data')
                BackupRecordFactory(
                    config=config,
                    filename=f'{config.name}_{i}.zip',
                    file_path=str(filepath),
                )

        service = RetentionService()
        total_deleted = service.enforce_all()

        # Only active config's 2 excess backups should be deleted
        assert total_deleted == 2
        # Inactive config should still have all 3
        assert BackupRecord.objects.filter(config=inactive, status='success').count() == 3

    def test_returns_total_count(self, temp_backup_dir):
        """Should return total deletion count across all configs."""
        config1 = PiholeConfigFactory(max_backups=2, max_age_days=0)
        config2 = PiholeConfigFactory(max_backups=1, max_age_days=0)

        # Config 1: 4 backups, 2 to delete
        for i in range(4):
            filepath = temp_backup_dir / f'config1_{i}.zip'
            filepath.write_bytes(b'test data')
            BackupRecordFactory(config=config1, file_path=str(filepath))

        # Config 2: 5 backups, 4 to delete
        for i in range(5):
            filepath = temp_backup_dir / f'config2_{i}.zip'
            filepath.write_bytes(b'test data')
            BackupRecordFactory(config=config2, file_path=str(filepath))

        service = RetentionService()
        total_deleted = service.enforce_all()

        assert total_deleted == 6

    def test_continues_on_error(self, temp_backup_dir):
        """Should continue processing other configs if one fails."""
        config1 = PiholeConfigFactory(max_backups=1, max_age_days=0)
        config2 = PiholeConfigFactory(max_backups=1, max_age_days=0)

        # Create backups for config2 only
        for i in range(3):
            filepath = temp_backup_dir / f'config2_{i}.zip'
            filepath.write_bytes(b'test data')
            BackupRecordFactory(config=config2, file_path=str(filepath))

        service = RetentionService()

        # Patch enforce_retention to fail for config1
        original_enforce = service.enforce_retention

        def mock_enforce(config):
            if config == config1:
                raise Exception('Simulated error')
            return original_enforce(config)

        with patch.object(service, 'enforce_retention', side_effect=mock_enforce):
            total_deleted = service.enforce_all()

        # Should have processed config2 despite config1 error
        assert total_deleted == 2


@pytest.mark.django_db
class TestRetentionServiceDeleteBackup:
    """Tests for RetentionService._delete_backup()."""

    def test_deletes_file_and_record(self, temp_backup_dir):
        """Should delete both file and database record."""
        config = PiholeConfigFactory()
        filepath = temp_backup_dir / 'test_delete.zip'
        filepath.write_bytes(b'test data')

        record = BackupRecordFactory(
            config=config,
            filename='test_delete.zip',
            file_path=str(filepath),
        )
        record_id = record.id

        service = RetentionService()
        service._delete_backup(record)

        assert not filepath.exists()
        assert not BackupRecord.objects.filter(id=record_id).exists()

    def test_handles_missing_file(self, temp_backup_dir):
        """Should delete record even if file is missing."""
        config = PiholeConfigFactory()

        record = BackupRecordFactory(
            config=config,
            filename='missing.zip',
            file_path='/nonexistent/missing.zip',
        )
        record_id = record.id

        service = RetentionService()
        # Should not raise exception
        service._delete_backup(record)

        assert not BackupRecord.objects.filter(id=record_id).exists()

    def test_handles_empty_file_path(self, temp_backup_dir):
        """Should handle empty file_path."""
        config = PiholeConfigFactory()

        record = FailedBackupRecordFactory(config=config)
        record_id = record.id

        service = RetentionService()
        service._delete_backup(record)

        assert not BackupRecord.objects.filter(id=record_id).exists()
