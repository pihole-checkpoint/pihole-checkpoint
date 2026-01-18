"""Backup restore service."""

import hashlib
import logging
from pathlib import Path

from ..models import BackupRecord, PiholeConfig
from .pihole_client import PiholeV6Client

logger = logging.getLogger(__name__)


class RestoreService:
    """Service for restoring backups to Pi-hole."""

    def __init__(self, config: PiholeConfig):
        self.config = config

    def _calculate_checksum(self, filepath: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def restore_backup(self, record: BackupRecord) -> dict:
        """
        Restore a backup to Pi-hole.

        Args:
            record: BackupRecord to restore

        Returns:
            API response from Pi-hole

        Raises:
            FileNotFoundError: Backup file missing
            ValueError: Checksum mismatch
            Exception: API errors
        """
        logger.info(f"Restoring backup {record.filename} to {self.config.name}")

        # Verify file exists
        filepath = Path(record.file_path)
        if not filepath.exists():
            raise FileNotFoundError(f"Backup file not found: {record.filename}")

        # Verify checksum before restore
        if record.checksum:
            actual_checksum = self._calculate_checksum(filepath)
            if actual_checksum != record.checksum:
                raise ValueError("Backup file corrupted (checksum mismatch)")

        # Upload to Pi-hole
        client = PiholeV6Client(
            base_url=self.config.pihole_url,
            password=self.config.password,
            verify_ssl=self.config.verify_ssl,
        )

        with open(filepath, "rb") as f:
            backup_data = f.read()

        result = client.upload_teleporter_backup(backup_data)
        logger.info(f"Backup {record.filename} restored successfully")
        return result
