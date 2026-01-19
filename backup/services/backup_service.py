"""Backup creation and management service."""

import hashlib
import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from ..models import BackupRecord, PiholeConfig
from .credential_service import CredentialService
from .notifications import NotificationEvent, NotificationPayload
from .notifications.service import get_notification_service
from .pihole_client import PiholeV6Client

logger = logging.getLogger(__name__)


class BackupService:
    """Service for creating and managing Pi-hole backups."""

    def __init__(self, config: PiholeConfig):
        self.config = config
        self.backup_dir = Path(settings.BACKUP_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.notification_service = get_notification_service()

    def _get_client(self) -> PiholeV6Client:
        """Create a Pi-hole client using environment credentials."""
        creds = CredentialService.get_credentials()
        return PiholeV6Client(
            base_url=creds["url"],
            password=creds["password"],
            verify_ssl=creds["verify_ssl"],
        )

    def _generate_filename(self) -> str:
        """Generate a unique filename for the backup."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.config.name.replace(" ", "_").lower()
        return f"pihole_checkpoint_{safe_name}_{timestamp}.zip"

    def _calculate_checksum(self, filepath: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def create_backup(self, is_manual: bool = False) -> BackupRecord:
        """
        Create a new backup from Pi-hole.

        Args:
            is_manual: Whether this backup was triggered manually

        Returns:
            BackupRecord on success

        Raises:
            Exception on failure
        """
        logger.info(f"Creating backup for {self.config.name} (manual={is_manual})")

        filename = self._generate_filename()
        filepath = self.backup_dir / filename

        try:
            # Download backup from Pi-hole
            client = self._get_client()
            backup_data = client.download_teleporter_backup()

            # Save to file
            with open(filepath, "wb") as f:
                f.write(backup_data)

            # Calculate checksum
            checksum = self._calculate_checksum(filepath)

            # Create record
            record = BackupRecord.objects.create(
                config=self.config,
                filename=filename,
                file_path=str(filepath),
                file_size=len(backup_data),
                checksum=checksum,
                status="success",
                is_manual=is_manual,
            )

            # Update config status
            self.config.last_successful_backup = timezone.now()
            self.config.last_backup_error = ""
            self.config.save(update_fields=["last_successful_backup", "last_backup_error"])

            logger.info(f"Backup created successfully: {filename}")

            # Send success notification
            self._notify(
                NotificationEvent.BACKUP_SUCCESS,
                "Backup Completed",
                f"Successfully created backup: {record.filename}",
                details={"File size": f"{record.file_size:,} bytes"},
            )

            return record

        except Exception as e:
            logger.error(f"Backup failed for {self.config.name}: {e}")

            # Clean up partial file if it exists
            if filepath.exists():
                filepath.unlink()

            # Create failed record
            record = BackupRecord.objects.create(
                config=self.config,
                filename=filename,
                file_path="",
                file_size=0,
                status="failed",
                error_message=str(e),
                is_manual=is_manual,
            )

            # Update config with error
            self.config.last_backup_error = str(e)
            self.config.save(update_fields=["last_backup_error"])

            # Send failure notification
            self._notify(
                NotificationEvent.BACKUP_FAILED,
                "Backup Failed",
                f"Failed to create backup: {e}",
                details={"Error": str(e)},
            )

            raise

    def delete_backup(self, record: BackupRecord) -> bool:
        """
        Delete a backup file and its record.

        Returns True if deleted successfully.
        """
        logger.info(f"Deleting backup: {record.filename}")

        # Delete file if it exists
        if record.file_path:
            filepath = Path(record.file_path)
            if filepath.exists():
                try:
                    filepath.unlink()
                except OSError as e:
                    logger.error(f"Failed to delete file {filepath}: {e}")
                    return False

        # Delete record
        record.delete()
        return True

    def get_backup_file(self, record: BackupRecord) -> Path | None:
        """Get the path to a backup file if it exists."""
        if not record.file_path:
            return None
        filepath = Path(record.file_path)
        return filepath if filepath.exists() else None

    def _notify(
        self,
        event: NotificationEvent,
        title: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        """Send notification for an event."""
        payload = NotificationPayload(
            event=event,
            title=title,
            message=message,
            pihole_name=self.config.name,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            details=details,
        )
        self.notification_service.send_notification(payload)
