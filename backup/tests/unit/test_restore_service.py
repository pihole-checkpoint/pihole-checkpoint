"""Unit tests for RestoreService."""

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backup.services.restore_service import RestoreService


@pytest.mark.django_db
class TestRestoreServiceRestoreBackup:
    """Tests for RestoreService.restore_backup()."""

    def test_restore_success(self, pihole_config, temp_backup_dir):
        """Successful restore should upload backup to Pi-hole."""
        # Create a backup file
        backup_content = b"PK\x03\x04test backup content"
        filepath = temp_backup_dir / "test_restore.zip"
        filepath.write_bytes(backup_content)

        # Calculate checksum
        checksum = hashlib.sha256(backup_content).hexdigest()

        # Create mock record
        record = MagicMock()
        record.file_path = str(filepath)
        record.filename = "test_restore.zip"
        record.checksum = checksum

        with patch("backup.services.restore_service.PiholeV6Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.upload_teleporter_backup.return_value = {"status": "success"}
            mock_client_class.return_value = mock_client

            service = RestoreService(pihole_config)
            result = service.restore_backup(record)

            assert result["status"] == "success"
            mock_client.upload_teleporter_backup.assert_called_once_with(backup_content)

    def test_restore_file_not_found(self, pihole_config):
        """Should raise FileNotFoundError when backup file doesn't exist."""
        record = MagicMock()
        record.file_path = "/nonexistent/backup.zip"
        record.filename = "backup.zip"

        service = RestoreService(pihole_config)

        with pytest.raises(FileNotFoundError, match="Backup file not found"):
            service.restore_backup(record)

    def test_restore_checksum_mismatch(self, pihole_config, temp_backup_dir):
        """Should raise ValueError when checksum doesn't match."""
        # Create a backup file
        filepath = temp_backup_dir / "test_restore.zip"
        filepath.write_bytes(b"PK\x03\x04test backup content")

        # Create mock record with wrong checksum
        record = MagicMock()
        record.file_path = str(filepath)
        record.filename = "test_restore.zip"
        record.checksum = "wrong_checksum_12345"

        service = RestoreService(pihole_config)

        with pytest.raises(ValueError, match="checksum mismatch"):
            service.restore_backup(record)

    def test_restore_no_checksum_skips_verification(self, pihole_config, temp_backup_dir):
        """Should skip checksum verification when record has no checksum."""
        backup_content = b"PK\x03\x04test backup content"
        filepath = temp_backup_dir / "test_restore.zip"
        filepath.write_bytes(backup_content)

        # Create mock record with no checksum
        record = MagicMock()
        record.file_path = str(filepath)
        record.filename = "test_restore.zip"
        record.checksum = None

        with patch("backup.services.restore_service.PiholeV6Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.upload_teleporter_backup.return_value = {"status": "success"}
            mock_client_class.return_value = mock_client

            service = RestoreService(pihole_config)
            result = service.restore_backup(record)

            assert result["status"] == "success"

    def test_restore_empty_checksum_skips_verification(self, pihole_config, temp_backup_dir):
        """Should skip checksum verification when record has empty checksum."""
        backup_content = b"PK\x03\x04test backup content"
        filepath = temp_backup_dir / "test_restore.zip"
        filepath.write_bytes(backup_content)

        # Create mock record with empty checksum
        record = MagicMock()
        record.file_path = str(filepath)
        record.filename = "test_restore.zip"
        record.checksum = ""

        with patch("backup.services.restore_service.PiholeV6Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.upload_teleporter_backup.return_value = {"status": "success"}
            mock_client_class.return_value = mock_client

            service = RestoreService(pihole_config)
            result = service.restore_backup(record)

            assert result["status"] == "success"

    def test_restore_creates_client_with_env_credentials(self, pihole_config, temp_backup_dir, settings):
        """Should create Pi-hole client with environment credentials."""
        backup_content = b"PK\x03\x04test backup content"
        filepath = temp_backup_dir / "test_restore.zip"
        filepath.write_bytes(backup_content)

        record = MagicMock()
        record.file_path = str(filepath)
        record.filename = "test_restore.zip"
        record.checksum = None

        with patch("backup.services.restore_service.PiholeV6Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.upload_teleporter_backup.return_value = {"status": "success"}
            mock_client_class.return_value = mock_client

            service = RestoreService(pihole_config)
            service.restore_backup(record)

            mock_client_class.assert_called_once_with(
                base_url=settings.PIHOLE_URL,
                password=settings.PIHOLE_PASSWORD,
                verify_ssl=settings.PIHOLE_VERIFY_SSL,
            )

    def test_restore_propagates_api_error(self, pihole_config, temp_backup_dir):
        """Should propagate API errors from Pi-hole client."""
        backup_content = b"PK\x03\x04test backup content"
        filepath = temp_backup_dir / "test_restore.zip"
        filepath.write_bytes(backup_content)

        record = MagicMock()
        record.file_path = str(filepath)
        record.filename = "test_restore.zip"
        record.checksum = None

        with patch("backup.services.restore_service.PiholeV6Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.upload_teleporter_backup.side_effect = ConnectionError("Cannot connect")
            mock_client_class.return_value = mock_client

            service = RestoreService(pihole_config)

            with pytest.raises(ConnectionError, match="Cannot connect"):
                service.restore_backup(record)


class TestRestoreServiceCalculateChecksum:
    """Tests for RestoreService._calculate_checksum()."""

    def test_calculate_checksum_returns_sha256(self, pihole_config):
        """Should return SHA256 checksum of file."""
        content = b"test content for checksum"
        expected_checksum = hashlib.sha256(content).hexdigest()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            filepath = Path(f.name)

        try:
            service = RestoreService(pihole_config)
            result = service._calculate_checksum(filepath)
            assert result == expected_checksum
        finally:
            filepath.unlink()
