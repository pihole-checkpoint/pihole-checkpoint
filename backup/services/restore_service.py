"""Backup restore service."""

import hashlib
import logging
from pathlib import Path

from ..models import BackupRecord, PiholeConfig
from .credential_service import CredentialService
from .notifications import NotificationEvent
from .notifications.service import get_notification_service, safe_send_notification
from .pihole_client import PiholeV6Client

logger = logging.getLogger(__name__)


class RestoreService:
    """Service for restoring backups to Pi-hole."""

    def __init__(self, config: PiholeConfig):
        self.config = config
        self.notification_service = get_notification_service()

    def _get_client(self) -> PiholeV6Client:
        """Create a Pi-hole client using environment credentials."""
        creds = CredentialService.get_credentials()
        return PiholeV6Client(
            base_url=creds["url"],
            password=creds["password"],
            verify_ssl=creds["verify_ssl"],
        )

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

        try:
            # Verify file exists
            filepath = Path(record.file_path)
            if not filepath.exists():
                raise FileNotFoundError(f"Backup file not found: {record.filename}")

            # Verify checksum before restore
            if record.checksum:
                actual_checksum = self._calculate_checksum(filepath)
                if actual_checksum != record.checksum:
                    raise ValueError("Backup file corrupted (checksum mismatch)")

            # Upload to Pi-hole using environment credentials
            client = self._get_client()

            with open(filepath, "rb") as f:
                backup_data = f.read()

            result = client.upload_teleporter_backup(backup_data)
            logger.info(f"Backup {record.filename} restored successfully")

            # Send success notification (isolated from restore success)
            safe_send_notification(
                self.notification_service,
                self.config.name,
                NotificationEvent.RESTORE_SUCCESS,
                "Restore Completed",
                f"Successfully restored backup: {record.filename}",
            )

            return result

        except Exception as e:
            logger.error(f"Restore failed for {record.filename}: {e}")

            # Send failure notification (isolated)
            safe_send_notification(
                self.notification_service,
                self.config.name,
                NotificationEvent.RESTORE_FAILED,
                "Restore Failed",
                f"Failed to restore backup: {record.filename}",
                details={"Error": str(e)},
            )

            raise
