from django.db import models
from encrypted_model_fields.fields import EncryptedCharField


class PiholeConfig(models.Model):
    """Configuration for a Pi-hole instance."""

    FREQUENCY_CHOICES = [
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
    ]

    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    name = models.CharField(max_length=100, default='Primary Pi-hole')
    pihole_url = models.URLField(help_text='e.g., https://192.168.1.100')
    password = EncryptedCharField(max_length=255)
    verify_ssl = models.BooleanField(default=False, help_text='Disable for self-signed certs')

    backup_frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default='daily')
    backup_time = models.TimeField(default='03:00', help_text='Time for daily/weekly backups')
    backup_day = models.SmallIntegerField(choices=DAY_CHOICES, default=0, help_text='Day for weekly backups')

    max_backups = models.PositiveIntegerField(default=10, help_text='Maximum number of backups to keep')
    max_age_days = models.PositiveIntegerField(default=30, help_text='Delete backups older than this')

    is_active = models.BooleanField(default=True, help_text='Enable scheduled backups')

    last_successful_backup = models.DateTimeField(null=True, blank=True)
    last_backup_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pi-hole Configuration'
        verbose_name_plural = 'Pi-hole Configurations'

    def __str__(self):
        return self.name


class BackupRecord(models.Model):
    """Record of a backup file."""

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    config = models.ForeignKey(PiholeConfig, on_delete=models.CASCADE, related_name='backups')
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)  # SHA256

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='success')
    error_message = models.TextField(blank=True)
    is_manual = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Backup Record'
        verbose_name_plural = 'Backup Records'

    def __str__(self):
        return f"{self.filename} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
