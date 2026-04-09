"""Unit tests for discovery_service."""

import os
from unittest.mock import patch

import pytest

from backup.models import BackupRecord, PiholeConfig
from backup.services.discovery_service import discover_instances_from_env


def _clean_env(extra=None):
    """Return os.environ with all PIHOLE_* keys removed, then add extra."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("PIHOLE_")}
    if extra:
        clean.update(extra)
    return clean


@pytest.mark.django_db
class TestDiscoverInstancesFromEnv:
    def test_discovers_instance_from_url(self):
        env = _clean_env({"PIHOLE_GYM_URL": "https://192.168.1.186", "PIHOLE_GYM_PASSWORD": "secret"})
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env()

        assert "GYM" in result["created"]
        config = PiholeConfig.objects.get(env_prefix="GYM")
        assert config.name == "Gym"

    def test_discovers_multiple_instances(self):
        env = _clean_env(
            {
                "PIHOLE_GYM_URL": "https://192.168.1.186",
                "PIHOLE_GYM_PASSWORD": "secret",
                "PIHOLE_BONUS_URL": "https://192.168.1.189",
                "PIHOLE_BONUS_PASSWORD": "secret2",
            }
        )
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env()

        assert sorted(result["created"]) == ["BONUS", "GYM"]
        assert PiholeConfig.objects.count() == 2

    def test_skips_existing_prefix(self):
        PiholeConfig.objects.create(name="Existing", env_prefix="GYM")
        env = _clean_env({"PIHOLE_GYM_URL": "https://192.168.1.186", "PIHOLE_GYM_PASSWORD": "secret"})
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env()

        assert "GYM" in result["skipped"]
        assert result["created"] == []

    def test_force_updates_existing(self):
        config = PiholeConfig.objects.create(name="Old Name", env_prefix="GYM")
        env = _clean_env(
            {
                "PIHOLE_GYM_URL": "https://192.168.1.186",
                "PIHOLE_GYM_PASSWORD": "secret",
                "PIHOLE_GYM_NAME": "New Name",
            }
        )
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env(force=True)

        assert "GYM" in result["updated"]
        config.refresh_from_db()
        assert config.name == "New Name"

    def test_no_env_vars(self):
        env = _clean_env({})
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env()

        assert result["created"] == []
        assert result["skipped"] == []
        assert result["updated"] == []

    def test_auto_generates_name_from_prefix(self):
        env = _clean_env({"PIHOLE_HOME_OFFICE_URL": "https://10.0.0.1", "PIHOLE_HOME_OFFICE_PASSWORD": "pw"})
        with patch.dict("os.environ", env, clear=True):
            discover_instances_from_env()

        config = PiholeConfig.objects.get(env_prefix="HOME_OFFICE")
        assert config.name == "Home Office"

    def test_custom_name_from_env(self):
        env = _clean_env(
            {
                "PIHOLE_GYM_URL": "https://192.168.1.186",
                "PIHOLE_GYM_PASSWORD": "secret",
                "PIHOLE_GYM_NAME": "Gym Pi-hole",
            }
        )
        with patch.dict("os.environ", env, clear=True):
            discover_instances_from_env()

        config = PiholeConfig.objects.get(env_prefix="GYM")
        assert config.name == "Gym Pi-hole"

    def test_optional_schedule_fields(self):
        env = _clean_env(
            {
                "PIHOLE_GYM_URL": "https://192.168.1.186",
                "PIHOLE_GYM_PASSWORD": "secret",
                "PIHOLE_GYM_SCHEDULE": "weekly",
                "PIHOLE_GYM_MAX_BACKUPS": "50",
                "PIHOLE_GYM_MAX_AGE_DAYS": "90",
            }
        )
        with patch.dict("os.environ", env, clear=True):
            discover_instances_from_env()

        config = PiholeConfig.objects.get(env_prefix="GYM")
        assert config.backup_frequency == "weekly"
        assert config.max_backups == 50
        assert config.max_age_days == 90

    def test_ignores_password_only_env_vars(self):
        """Should not create instance if only PASSWORD is set (no URL)."""
        env = _clean_env({"PIHOLE_GYM_PASSWORD": "secret"})
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env()

        assert result["created"] == []
        assert PiholeConfig.objects.count() == 0

    def test_invalid_schedule_uses_default(self):
        env = _clean_env(
            {
                "PIHOLE_GYM_URL": "https://192.168.1.186",
                "PIHOLE_GYM_PASSWORD": "secret",
                "PIHOLE_GYM_SCHEDULE": "biweekly",
            }
        )
        with patch.dict("os.environ", env, clear=True):
            discover_instances_from_env()

        config = PiholeConfig.objects.get(env_prefix="GYM")
        assert config.backup_frequency == "daily"  # model default

    def test_marks_instance_not_configured_when_env_var_gone(self):
        """Instance should be marked not_configured when its env var is removed (default behavior)."""
        PiholeConfig.objects.create(name="Old Instance", env_prefix="OLD")
        env = _clean_env({"PIHOLE_GYM_URL": "https://192.168.1.186", "PIHOLE_GYM_PASSWORD": "secret"})
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env()

        assert result["removed"] == []
        old = PiholeConfig.objects.get(env_prefix="OLD")
        assert old.connection_status == "not_configured"
        assert "GYM" in result["created"]

    def test_removes_instance_when_prune_enabled(self):
        """Instance should be removed when PRUNE_STALE_INSTANCES=true."""
        PiholeConfig.objects.create(name="Old Instance", env_prefix="OLD")
        env = _clean_env(
            {
                "PIHOLE_GYM_URL": "https://192.168.1.186",
                "PIHOLE_GYM_PASSWORD": "secret",
                "PRUNE_STALE_INSTANCES": "true",
            }
        )
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env()

        assert "OLD" in result["removed"]
        assert not PiholeConfig.objects.filter(env_prefix="OLD").exists()
        assert "GYM" in result["created"]

    def test_removes_backup_files_on_instance_removal(self, tmp_path, settings):
        """Removing an instance should also delete its backup files from disk."""
        settings.BACKUP_DIR = tmp_path
        config = PiholeConfig.objects.create(name="Old", env_prefix="OLD")
        backup_file = tmp_path / "old_backup.zip"
        backup_file.write_bytes(b"fake zip")
        BackupRecord.objects.create(
            config=config,
            filename="old_backup.zip",
            file_path=str(backup_file),
            file_size=8,
            status="success",
        )

        env = _clean_env({"PRUNE_STALE_INSTANCES": "true"})
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env()

        assert "OLD" in result["removed"]
        assert not backup_file.exists()
        assert not BackupRecord.objects.filter(config=config).exists()

    def test_does_not_remove_instance_with_env_var_present(self):
        """Instance should NOT be removed when its env var is still set."""
        PiholeConfig.objects.create(name="Gym", env_prefix="GYM")
        env = _clean_env({"PIHOLE_GYM_URL": "https://192.168.1.186", "PIHOLE_GYM_PASSWORD": "secret"})
        with patch.dict("os.environ", env, clear=True):
            result = discover_instances_from_env()

        assert result["removed"] == []
        assert "GYM" in result["skipped"]
