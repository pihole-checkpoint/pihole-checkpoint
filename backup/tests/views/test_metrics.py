"""Tests for the Prometheus /metrics/ endpoint."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone as dj_timezone

from backup.models import BackupRecord
from backup.tests.factories import (
    BackupRecordFactory,
    FailedBackupRecordFactory,
    PiholeConfigFactory,
)


@pytest.fixture(autouse=True)
def scheduler_running():
    with patch("backup.services.metrics_service.is_scheduler_running", return_value=True) as m:
        yield m


@pytest.mark.django_db
def test_metrics_returns_text_exposition(client):
    response = client.get(reverse("metrics"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    body = response.content.decode()
    assert "# HELP pihole_info" in body
    assert "# TYPE pihole_info gauge" in body
    assert "# HELP pihole_scheduler_up" in body
    assert "pihole_scheduler_up 1.0" in body


@pytest.mark.django_db
def test_metrics_auth_exempt(client, auth_enabled_settings):
    response = client.get(reverse("metrics"))
    assert response.status_code == 200
    assert "pihole_info" in response.content.decode()


@pytest.mark.django_db
def test_metrics_auth_exempt_no_trailing_slash(client, auth_enabled_settings):
    # Prometheus's default metrics_path is /metrics (no trailing slash); must serve directly, not redirect.
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert "pihole_info" in response.content.decode()


@pytest.mark.django_db
def test_metrics_scheduler_down(client, scheduler_running):
    scheduler_running.return_value = False
    response = client.get(reverse("metrics"))
    assert response.status_code == 200
    assert "pihole_scheduler_up 0.0" in response.content.decode()


@pytest.mark.django_db
def test_metrics_empty_configs(client):
    response = client.get(reverse("metrics"))
    body = response.content.decode()
    # No configs, so config-scoped metrics emit only HELP/TYPE with no samples
    assert "# HELP pihole_config_active" in body
    assert "# TYPE pihole_config_active gauge" in body
    assert not any(ln.startswith("pihole_config_active{") for ln in body.splitlines())
    assert not any(ln.startswith("pihole_backup_records{") for ln in body.splitlines())


@pytest.mark.django_db
def test_metrics_per_config_labels(client):
    a = PiholeConfigFactory(name="Alpha", env_prefix="ALPHA")
    b = PiholeConfigFactory(name="Beta", env_prefix="BETA", is_active=False)
    BackupRecordFactory(config=a, file_size=100)
    BackupRecordFactory(config=a, file_size=250)
    FailedBackupRecordFactory(config=a)
    BackupRecordFactory(config=b, file_size=500)

    response = client.get(reverse("metrics"))
    body = response.content.decode()

    assert f'pihole_config_info{{config_id="{a.id}",config_name="Alpha"}} 1.0' in body
    assert f'pihole_config_info{{config_id="{b.id}",config_name="Beta"}} 1.0' in body
    assert f'pihole_config_active{{config_id="{a.id}"}} 1.0' in body
    assert f'pihole_config_active{{config_id="{b.id}"}} 0.0' in body

    # Alpha: 2 success, 1 failed
    assert f'pihole_backup_records{{config_id="{a.id}",status="success"}} 2.0' in body
    assert f'pihole_backup_records{{config_id="{a.id}",status="failed"}} 1.0' in body

    # Alpha total size: 100 + 250 = 350; most recent successful = 250
    assert f'pihole_backup_total_size_bytes{{config_id="{a.id}"}} 350.0' in body
    assert f'pihole_backup_file_size_bytes{{config_id="{a.id}"}} 250.0' in body


@pytest.mark.django_db
def test_metrics_last_success_timestamp(client):
    ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    config = PiholeConfigFactory(
        name="TS",
        env_prefix="TS",
        last_successful_backup=ts,
    )

    response = client.get(reverse("metrics"))
    body = response.content.decode()

    line_prefix = f'pihole_backup_last_success_timestamp_seconds{{config_id="{config.id}"}} '
    line = next(ln for ln in body.splitlines() if ln.startswith(line_prefix))
    emitted = float(line[len(line_prefix) :])
    assert emitted == pytest.approx(ts.timestamp())


@pytest.mark.django_db
def test_metrics_latest_picks_by_created_at_not_id(client):
    # Newest by id is oldest by created_at — metrics must follow created_at.
    config = PiholeConfigFactory(name="Ord", env_prefix="ORD")
    older_by_time = BackupRecordFactory(config=config, file_size=111)
    newer_by_time = BackupRecordFactory(config=config, file_size=222)
    # Force the higher-id record to be older than the lower-id one.
    old_time = dj_timezone.now() - timedelta(days=5)
    BackupRecord.objects.filter(pk=newer_by_time.pk).update(created_at=old_time)
    newer_by_time.refresh_from_db()
    assert newer_by_time.created_at < older_by_time.created_at
    assert newer_by_time.pk > older_by_time.pk

    response = client.get(reverse("metrics"))
    body = response.content.decode()

    # last size should reflect the record with the most recent created_at (file_size=111).
    assert f'pihole_backup_file_size_bytes{{config_id="{config.id}"}} 111.0' in body


@pytest.mark.django_db
def test_metrics_connection_status_one_hot(client):
    config = PiholeConfigFactory(name="Conn", env_prefix="CONN", connection_status="auth_error")

    response = client.get(reverse("metrics"))
    body = response.content.decode()

    assert f'pihole_connection_status{{config_id="{config.id}",status="auth_error"}} 1.0' in body
    assert f'pihole_connection_status{{config_id="{config.id}",status="ok"}} 0.0' in body
