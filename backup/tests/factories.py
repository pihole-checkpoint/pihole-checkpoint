"""Factory classes for creating test model instances."""

from datetime import time

import factory

from backup.models import BackupRecord, PiholeConfig


class PiholeConfigFactory(factory.django.DjangoModelFactory):
    """Factory for creating PiholeConfig instances."""

    class Meta:
        model = PiholeConfig

    name = factory.Sequence(lambda n: f"Pi-hole {n}")
    pihole_url = factory.Sequence(lambda n: f"https://pihole{n}.local")
    password = "testpassword123"
    verify_ssl = False
    backup_frequency = "daily"
    backup_time = time(3, 0)
    backup_day = 0
    max_backups = 10
    max_age_days = 30
    is_active = True
    last_successful_backup = None
    last_backup_error = ""


class InactivePiholeConfigFactory(PiholeConfigFactory):
    """Factory for creating inactive PiholeConfig instances."""

    is_active = False


class HourlyPiholeConfigFactory(PiholeConfigFactory):
    """Factory for creating hourly backup PiholeConfig instances."""

    backup_frequency = "hourly"


class WeeklyPiholeConfigFactory(PiholeConfigFactory):
    """Factory for creating weekly backup PiholeConfig instances."""

    backup_frequency = "weekly"
    backup_day = 0  # Monday


class BackupRecordFactory(factory.django.DjangoModelFactory):
    """Factory for creating BackupRecord instances."""

    class Meta:
        model = BackupRecord

    config = factory.SubFactory(PiholeConfigFactory)
    filename = factory.Sequence(lambda n: f"pihole_backup_{n}.zip")
    file_path = factory.LazyAttribute(lambda obj: f"/app/backups/{obj.filename}")
    file_size = 1024
    checksum = factory.Sequence(lambda n: f"checksum{n:064d}"[:64])
    status = "success"
    error_message = ""
    is_manual = False


class FailedBackupRecordFactory(BackupRecordFactory):
    """Factory for creating failed BackupRecord instances."""

    file_path = ""
    file_size = 0
    checksum = ""
    status = "failed"
    error_message = "Connection failed"


class ManualBackupRecordFactory(BackupRecordFactory):
    """Factory for creating manual backup instances."""

    is_manual = True


class OldBackupRecordFactory(BackupRecordFactory):
    """Factory for creating old backup records (for retention testing)."""

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override create to set old created_at timestamp."""
        from datetime import timedelta

        from django.utils import timezone

        days_old = kwargs.pop("days_old", 60)
        obj = super()._create(model_class, *args, **kwargs)

        # Update created_at to be old
        old_time = timezone.now() - timedelta(days=days_old)
        BackupRecord.objects.filter(pk=obj.pk).update(created_at=old_time)
        obj.refresh_from_db()
        return obj
