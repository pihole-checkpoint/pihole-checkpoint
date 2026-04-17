"""Prometheus metrics collector.

Builds a fresh CollectorRegistry on each scrape by querying the Django ORM.
The database is the authoritative source of backup state (ADR-0016), so
reading from it keeps the scheduler and web processes decoupled.
"""

from importlib.metadata import PackageNotFoundError, version

from django.db.models import Count, Max, Sum
from prometheus_client import CollectorRegistry, Gauge

from backup.models import BackupRecord, PiholeConfig
from backup.services.system_service import is_scheduler_running

try:
    _APP_VERSION = version("pihole-checkpoint")
except PackageNotFoundError:
    _APP_VERSION = "unknown"

CONFIG_LABELS = ("config_id", "config_name")


def build_registry() -> CollectorRegistry:
    """Return a CollectorRegistry populated with current metric values."""
    registry = CollectorRegistry()

    info = Gauge(
        "pihole_info",
        "Pi-hole Checkpoint build information.",
        ("version",),
        registry=registry,
    )
    info.labels(version=_APP_VERSION).set(1)

    scheduler_up = Gauge(
        "pihole_scheduler_up",
        "1 if the APScheduler process is running, 0 otherwise.",
        registry=registry,
    )
    scheduler_up.set(1 if is_scheduler_running() else 0)

    config_active = Gauge(
        "pihole_config_active",
        "1 if the Pi-hole configuration has scheduled backups enabled.",
        CONFIG_LABELS,
        registry=registry,
    )
    connection_status = Gauge(
        "pihole_connection_status",
        "1 for the current connection_status of each config (one-hot encoded).",
        (*CONFIG_LABELS, "status"),
        registry=registry,
    )
    last_success_ts = Gauge(
        "pihole_backup_last_success_timestamp_seconds",
        "Unix timestamp of the last successful backup (0 if none).",
        CONFIG_LABELS,
        registry=registry,
    )
    last_status = Gauge(
        "pihole_backup_last_status",
        "Status of the most recent backup attempt (1=success, 0=failed, -1=none).",
        CONFIG_LABELS,
        registry=registry,
    )
    backups_total = Gauge(
        "pihole_backups_total",
        "Total number of backup records per config and status.",
        (*CONFIG_LABELS, "status"),
        registry=registry,
    )
    last_size = Gauge(
        "pihole_backup_file_size_bytes",
        "Size in bytes of the most recent successful backup.",
        CONFIG_LABELS,
        registry=registry,
    )
    total_size = Gauge(
        "pihole_backup_total_size_bytes",
        "Sum of file sizes across all successful backups for a config.",
        CONFIG_LABELS,
        registry=registry,
    )

    status_choices = [c[0] for c in PiholeConfig.CONNECTION_STATUS_CHOICES]
    backup_status_choices = [c[0] for c in BackupRecord.STATUS_CHOICES]

    per_config_counts = {
        (row["config_id"], row["status"]): row["n"]
        for row in BackupRecord.objects.values("config_id", "status").annotate(n=Count("id"))
    }
    per_config_success = {
        row["config_id"]: row
        for row in BackupRecord.objects.filter(status="success")
        .values("config_id")
        .annotate(total=Sum("file_size"), latest_id=Max("id"))
    }
    latest_record_ids = [row["latest_id"] for row in per_config_success.values() if row["latest_id"]]
    latest_records = {r.config_id: r for r in BackupRecord.objects.filter(id__in=latest_record_ids)}
    latest_any = {
        row["config_id"]: row["latest_id"]
        for row in BackupRecord.objects.values("config_id").annotate(latest_id=Max("id"))
    }
    latest_any_records = {r.id: r for r in BackupRecord.objects.filter(id__in=list(latest_any.values()))}

    for config in PiholeConfig.objects.all():
        labels = {"config_id": str(config.id), "config_name": config.name}

        config_active.labels(**labels).set(1 if config.is_active else 0)

        for status in status_choices:
            connection_status.labels(**labels, status=status).set(1 if config.connection_status == status else 0)

        last_success_ts.labels(**labels).set(
            config.last_successful_backup.timestamp() if config.last_successful_backup else 0
        )

        latest_id = latest_any.get(config.id)
        latest = latest_any_records.get(latest_id) if latest_id else None
        if latest is None:
            last_status.labels(**labels).set(-1)
        else:
            last_status.labels(**labels).set(1 if latest.status == "success" else 0)

        for status in backup_status_choices:
            backups_total.labels(**labels, status=status).set(per_config_counts.get((config.id, status), 0))

        success_row = per_config_success.get(config.id)
        if success_row:
            total_size.labels(**labels).set(success_row["total"] or 0)
            latest_success = latest_records.get(config.id)
            last_size.labels(**labels).set(latest_success.file_size if latest_success else 0)
        else:
            total_size.labels(**labels).set(0)
            last_size.labels(**labels).set(0)

    return registry
