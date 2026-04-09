"""Auto-discover Pi-hole instances from PIHOLE_* environment variables."""

import logging
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

from backup.models import PiholeConfig

logger = logging.getLogger(__name__)

# Fields recognized after PIHOLE_{PREFIX}_
_KNOWN_FIELDS = {"URL", "PASSWORD", "VERIFY_SSL", "NAME", "SCHEDULE", "TIME", "DAY", "MAX_BACKUPS", "MAX_AGE_DAYS"}

_ENV_PATTERN = re.compile(r"^PIHOLE_([A-Z][A-Z0-9_]*?)_(" + "|".join(_KNOWN_FIELDS) + r")$")


def _extract_prefixes():
    """Scan os.environ for PIHOLE_*_URL variables.

    Returns a set of discovered prefixes.
    """
    prefixes = set()
    for key in os.environ:
        match = _ENV_PATTERN.match(key)
        if match and match.group(2) == "URL":
            prefixes.add(match.group(1))
    return prefixes


_VALID_FREQUENCIES = {"hourly", "daily", "weekly"}
_VALID_DAYS = set(range(7))  # 0=Monday .. 6=Sunday


def _build_config_kwargs(prefix):
    """Build kwargs dict for PiholeConfig creation from env vars."""
    kwargs = {
        "env_prefix": prefix,
        "name": os.environ.get(
            f"PIHOLE_{prefix}_NAME",
            prefix.replace("_", " ").title(),
        ),
    }

    env_map = {
        "SCHEDULE": ("backup_frequency", str),
        "TIME": ("backup_time", str),
        "DAY": ("backup_day", int),
        "MAX_BACKUPS": ("max_backups", int),
        "MAX_AGE_DAYS": ("max_age_days", int),
    }
    for env_suffix, (field_name, converter) in env_map.items():
        value = os.environ.get(f"PIHOLE_{prefix}_{env_suffix}")
        if value is not None:
            try:
                kwargs[field_name] = converter(value)
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid value for PIHOLE_%s_%s=%r, skipping",
                    prefix,
                    env_suffix,
                    value,
                )
                continue

    # Validate enum fields
    freq = kwargs.get("backup_frequency")
    if freq is not None and freq not in _VALID_FREQUENCIES:
        logger.warning("Invalid PIHOLE_%s_SCHEDULE=%r, using default 'daily'", prefix, freq)
        del kwargs["backup_frequency"]

    day = kwargs.get("backup_day")
    if day is not None and day not in _VALID_DAYS:
        logger.warning("Invalid PIHOLE_%s_DAY=%r, using default 0", prefix, day)
        del kwargs["backup_day"]

    return kwargs


def _delete_backup_files(config):
    """Delete backup files from disk for a config instance."""
    backup_dir = Path(settings.BACKUP_DIR).resolve()
    for record in config.backups.all():
        if not record.file_path:
            continue
        filepath = Path(record.file_path).resolve()
        try:
            filepath.relative_to(backup_dir)
        except ValueError:
            logger.warning("Skipping file outside backup dir: %s", filepath)
            continue
        if filepath.exists():
            try:
                filepath.unlink()
            except OSError as e:
                logger.error("Failed to delete backup file %s: %s", filepath, e)


def discover_instances_from_env(force=False):
    """Scan environment for PIHOLE_*_URL vars, create/update/remove PiholeConfig rows.

    Instances whose PIHOLE_{PREFIX}_URL env var is no longer present are removed
    along with their backup records and files.

    Args:
        force: If True, re-apply env var values to existing instances
               (except credentials, which are always runtime).

    Returns:
        dict with "created", "skipped", "updated", and "removed" lists of prefixes.
    """
    prefixes = _extract_prefixes()
    created, skipped, updated, removed = [], [], [], []

    # Remove instances whose env vars are gone
    for config in PiholeConfig.objects.all():
        if config.env_prefix not in prefixes:
            logger.info(
                "Removing instance %s (pk=%d) — PIHOLE_%s_URL no longer set",
                config.name,
                config.pk,
                config.env_prefix,
            )
            _delete_backup_files(config)
            removed.append(config.env_prefix)
            config.delete()

    for prefix in sorted(prefixes):
        existing = PiholeConfig.objects.filter(env_prefix=prefix).first()

        if existing and not force:
            logger.debug(
                "Instance with env_prefix=%s already exists (pk=%d), skipping",
                prefix,
                existing.pk,
            )
            skipped.append(prefix)
            continue

        try:
            kwargs = _build_config_kwargs(prefix)
        except (ValueError, TypeError):
            logger.exception("Invalid env var value for prefix %s, skipping", prefix)
            continue

        if existing and force:
            for field, value in kwargs.items():
                if field != "env_prefix":
                    setattr(existing, field, value)
            try:
                existing.full_clean()
                existing.save()
            except (ValidationError, ValueError) as exc:
                logger.warning(
                    "Invalid config for prefix %s, skipping update: %s",
                    prefix,
                    exc,
                )
                continue
            logger.info("Updated instance %s (pk=%d) from env vars", prefix, existing.pk)
            updated.append(prefix)
        else:
            config = PiholeConfig(**kwargs)
            try:
                config.full_clean()
                config.save()
            except (ValidationError, ValueError) as exc:
                logger.warning(
                    "Invalid config for prefix %s, skipping creation: %s",
                    prefix,
                    exc,
                )
                continue
            logger.info("Created instance %s (pk=%d) from env vars", prefix, config.pk)
            created.append(prefix)

    return {"created": created, "skipped": skipped, "updated": updated, "removed": removed}
