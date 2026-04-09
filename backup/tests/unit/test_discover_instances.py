"""Unit tests for discover_instances management command."""

import pytest
from django.core.management import call_command

from backup.models import PiholeConfig


@pytest.mark.django_db
class TestDiscoverInstances:
    """Tests for the discover_instances management command."""

    def test_creates_config_from_env(self, monkeypatch):
        """Should create PiholeConfig for discovered prefixes."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://primary.local")
        monkeypatch.setenv("PIHOLE_PRIMARY_PASSWORD", "pass1")

        call_command("discover_instances")

        assert PiholeConfig.objects.count() == 1
        config = PiholeConfig.objects.first()
        assert config.env_prefix == "PRIMARY"
        assert config.name == "Primary"

    def test_creates_multiple_configs(self, monkeypatch):
        """Should create configs for all discovered prefixes."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://primary.local")
        monkeypatch.setenv("PIHOLE_SECONDARY_URL", "https://secondary.local")

        call_command("discover_instances")

        assert PiholeConfig.objects.count() == 2
        prefixes = set(PiholeConfig.objects.values_list("env_prefix", flat=True))
        assert prefixes == {"PRIMARY", "SECONDARY"}

    def test_skips_existing_configs(self, monkeypatch, db):
        """Should not duplicate existing configs."""
        PiholeConfig.objects.create(env_prefix="PRIMARY", name="My Pi-hole")
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://primary.local")

        call_command("discover_instances")

        assert PiholeConfig.objects.count() == 1
        config = PiholeConfig.objects.first()
        assert config.name == "My Pi-hole"  # Name not overwritten

    def test_no_env_vars_warns(self, monkeypatch, capsys):
        """Should warn when no Pi-hole env vars found."""
        monkeypatch.delenv("PIHOLE_PRIMARY_URL", raising=False)

        call_command("discover_instances")

        output = capsys.readouterr().out
        assert "No Pi-hole instances" in output

    def test_idempotent(self, monkeypatch):
        """Running twice should not create duplicates."""
        monkeypatch.setenv("PIHOLE_PRIMARY_URL", "https://primary.local")

        call_command("discover_instances")
        call_command("discover_instances")

        assert PiholeConfig.objects.count() == 1
