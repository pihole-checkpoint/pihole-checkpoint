"""Unit tests for system service utilities."""

from unittest.mock import MagicMock, patch

from backup.services.system_service import is_scheduler_running


class TestIsSchedulerRunning:
    """Tests for is_scheduler_running function."""

    def test_returns_true_when_scheduler_found(self):
        """Should return True when runapscheduler process is found."""
        with patch("os.listdir") as mock_listdir:
            mock_listdir.return_value = ["1", "123", "self", "456"]

            # Mock opening cmdline files
            def mock_open_cmdline(path, mode="r"):
                mock_file = MagicMock()
                if path == "/proc/123/cmdline":
                    mock_file.__enter__ = MagicMock(return_value=mock_file)
                    mock_file.__exit__ = MagicMock(return_value=False)
                    mock_file.read.return_value = b"python\x00manage.py\x00runapscheduler"
                    return mock_file
                else:
                    mock_file.__enter__ = MagicMock(return_value=mock_file)
                    mock_file.__exit__ = MagicMock(return_value=False)
                    mock_file.read.return_value = b"some\x00other\x00process"
                    return mock_file

            with patch("builtins.open", mock_open_cmdline):
                assert is_scheduler_running() is True

    def test_returns_false_when_scheduler_not_found(self):
        """Should return False when runapscheduler process is not found."""
        with patch("os.listdir") as mock_listdir:
            mock_listdir.return_value = ["1", "123"]

            def mock_open_cmdline(path, mode="r"):
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.read.return_value = b"some\x00other\x00process"
                return mock_file

            with patch("builtins.open", mock_open_cmdline):
                assert is_scheduler_running() is False

    def test_skips_non_numeric_entries(self):
        """Should skip non-numeric /proc entries like 'self', 'net', etc."""
        with patch("os.listdir") as mock_listdir:
            mock_listdir.return_value = ["self", "net", "sys", "123"]

            def mock_open_cmdline(path, mode="r"):
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                if path == "/proc/123/cmdline":
                    mock_file.read.return_value = b"runapscheduler"
                else:
                    # Should not be called for non-numeric entries
                    raise AssertionError(f"Should not open {path}")
                return mock_file

            with patch("builtins.open", mock_open_cmdline):
                assert is_scheduler_running() is True

    def test_handles_file_not_found(self):
        """Should handle FileNotFoundError when process exits during scan."""
        with patch("os.listdir") as mock_listdir:
            mock_listdir.return_value = ["123", "456"]

            call_count = [0]

            def mock_open_cmdline(path, mode="r"):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise FileNotFoundError("Process exited")
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.read.return_value = b"runapscheduler"
                return mock_file

            with patch("builtins.open", mock_open_cmdline):
                # Should continue and find the scheduler in second process
                assert is_scheduler_running() is True

    def test_handles_permission_error(self):
        """Should handle PermissionError for processes we cannot read."""
        with patch("os.listdir") as mock_listdir:
            mock_listdir.return_value = ["1", "123"]

            call_count = [0]

            def mock_open_cmdline(path, mode="r"):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise PermissionError("Access denied")
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_file.read.return_value = b"runapscheduler"
                return mock_file

            with patch("builtins.open", mock_open_cmdline):
                assert is_scheduler_running() is True

    def test_returns_false_when_proc_not_accessible(self):
        """Should return False when /proc is not accessible."""
        with patch("os.listdir") as mock_listdir:
            mock_listdir.side_effect = PermissionError("Cannot access /proc")

            assert is_scheduler_running() is False

    def test_returns_false_on_unexpected_exception(self):
        """Should return False and log warning on unexpected errors."""
        with patch("os.listdir") as mock_listdir:
            mock_listdir.side_effect = RuntimeError("Unexpected error")

            with patch("backup.services.system_service.logger") as mock_logger:
                result = is_scheduler_running()

                assert result is False
                mock_logger.warning.assert_called_once()

    def test_handles_utf8_decode_errors(self):
        """Should handle invalid UTF-8 in cmdline gracefully."""
        with patch("os.listdir") as mock_listdir:
            mock_listdir.return_value = ["123"]

            def mock_open_cmdline(path, mode="r"):
                mock_file = MagicMock()
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                # Invalid UTF-8 bytes
                mock_file.read.return_value = b"\xff\xfe runapscheduler"
                return mock_file

            with patch("builtins.open", mock_open_cmdline):
                # Should handle decode errors and still find the scheduler
                assert is_scheduler_running() is True

    def test_empty_proc_directory(self):
        """Should return False when /proc has no process entries."""
        with patch("os.listdir") as mock_listdir:
            mock_listdir.return_value = ["self", "net", "sys"]

            assert is_scheduler_running() is False
