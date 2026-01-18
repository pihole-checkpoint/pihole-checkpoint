"""Integration tests for scheduler functionality."""

from datetime import time
from unittest.mock import MagicMock, patch

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backup.management.commands.runapscheduler import (
    Command,
    run_backup_job,
    run_retention_job,
)
from backup.tests.factories import (
    HourlyPiholeConfigFactory,
    InactivePiholeConfigFactory,
    PiholeConfigFactory,
    WeeklyPiholeConfigFactory,
)


@pytest.mark.django_db
@pytest.mark.integration
class TestRunBackupJob:
    """Tests for run_backup_job function."""

    def test_creates_backups_for_active_configs(self, temp_backup_dir, sample_backup_data):
        """run_backup_job should create backups for all active configs."""
        PiholeConfigFactory(name="Active 1")
        PiholeConfigFactory(name="Active 2")

        with patch("backup.management.commands.runapscheduler.BackupService") as mock_service_class:
            mock_service = MagicMock()
            mock_record = MagicMock()
            mock_record.filename = "test.zip"
            mock_service.create_backup.return_value = mock_record
            mock_service_class.return_value = mock_service

            run_backup_job()

            # Should have created service for each config
            assert mock_service_class.call_count == 2
            # Should have called create_backup for each
            assert mock_service.create_backup.call_count == 2

    def test_skips_inactive_configs(self, temp_backup_dir):
        """run_backup_job should skip inactive configs."""
        active = PiholeConfigFactory(name="Active")
        InactivePiholeConfigFactory(name="Inactive")

        with patch("backup.management.commands.runapscheduler.BackupService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.create_backup.return_value = MagicMock(filename="test.zip")
            mock_service_class.return_value = mock_service

            run_backup_job()

            # Should only be called for active config
            assert mock_service_class.call_count == 1
            mock_service_class.assert_called_with(active)

    def test_continues_on_failure(self, temp_backup_dir):
        """run_backup_job should continue if one config fails."""
        PiholeConfigFactory(name="Will Fail")
        PiholeConfigFactory(name="Will Succeed")

        with patch("backup.management.commands.runapscheduler.BackupService") as mock_service_class:
            mock_service = MagicMock()

            # First call fails, second succeeds
            mock_service.create_backup.side_effect = [
                Exception("Backup failed"),
                MagicMock(filename="success.zip"),
            ]
            mock_service_class.return_value = mock_service

            # Should not raise exception
            run_backup_job()

            # Both configs should have been attempted
            assert mock_service.create_backup.call_count == 2


@pytest.mark.django_db
@pytest.mark.integration
class TestRunRetentionJob:
    """Tests for run_retention_job function."""

    def test_calls_enforce_all(self, temp_backup_dir):
        """run_retention_job should call RetentionService.enforce_all()."""
        with patch("backup.management.commands.runapscheduler.RetentionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.enforce_all.return_value = 5
            mock_service_class.return_value = mock_service

            run_retention_job()

            mock_service.enforce_all.assert_called_once()

    def test_handles_errors(self, temp_backup_dir):
        """run_retention_job should handle errors gracefully."""
        with patch("backup.management.commands.runapscheduler.RetentionService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.enforce_all.side_effect = Exception("Retention failed")
            mock_service_class.return_value = mock_service

            # Should not raise exception
            run_retention_job()


@pytest.mark.django_db
@pytest.mark.integration
class TestScheduleBackupJobs:
    """Tests for Command._schedule_backup_jobs()."""

    def test_hourly_config_uses_interval_trigger(self, temp_backup_dir):
        """Hourly backup config should use IntervalTrigger."""
        HourlyPiholeConfigFactory()

        mock_scheduler = MagicMock()
        command = Command()

        command._schedule_backup_jobs(mock_scheduler)

        # Verify add_job was called
        mock_scheduler.add_job.assert_called()

        # Get the call args
        call_kwargs = mock_scheduler.add_job.call_args_list[-1].kwargs
        trigger = call_kwargs.get("trigger")

        assert isinstance(trigger, IntervalTrigger)

    def test_daily_config_uses_cron_trigger(self, temp_backup_dir):
        """Daily backup config should use CronTrigger."""
        PiholeConfigFactory(backup_frequency="daily", backup_time=time(3, 30))

        mock_scheduler = MagicMock()
        command = Command()

        command._schedule_backup_jobs(mock_scheduler)

        call_kwargs = mock_scheduler.add_job.call_args_list[-1].kwargs
        trigger = call_kwargs.get("trigger")

        assert isinstance(trigger, CronTrigger)

    def test_weekly_config_uses_cron_trigger_with_day(self, temp_backup_dir):
        """Weekly backup config should use CronTrigger with day_of_week."""
        WeeklyPiholeConfigFactory(
            backup_day=2,  # Wednesday
            backup_time=time(4, 0),
        )

        mock_scheduler = MagicMock()
        command = Command()

        command._schedule_backup_jobs(mock_scheduler)

        call_kwargs = mock_scheduler.add_job.call_args_list[-1].kwargs
        trigger = call_kwargs.get("trigger")

        assert isinstance(trigger, CronTrigger)

    def test_removes_existing_job_before_adding_new(self, temp_backup_dir):
        """Should remove existing job before adding new one."""
        config = PiholeConfigFactory()

        mock_scheduler = MagicMock()
        command = Command()

        command._schedule_backup_jobs(mock_scheduler)

        # Should attempt to remove existing job
        expected_job_id = f"backup_{config.id}"
        mock_scheduler.remove_job.assert_called_with(expected_job_id)

    def test_skips_inactive_configs(self, temp_backup_dir):
        """Should skip inactive configs."""
        active = PiholeConfigFactory()
        inactive = InactivePiholeConfigFactory()

        mock_scheduler = MagicMock()
        command = Command()

        command._schedule_backup_jobs(mock_scheduler)

        # Should only add job for active config
        job_ids = [call.kwargs.get("id") for call in mock_scheduler.add_job.call_args_list]
        assert f"backup_{active.id}" in job_ids
        assert f"backup_{inactive.id}" not in job_ids

    def test_handles_remove_job_exception(self, temp_backup_dir):
        """Should handle exception when removing non-existent job."""
        PiholeConfigFactory()

        mock_scheduler = MagicMock()
        mock_scheduler.remove_job.side_effect = Exception("Job not found")

        command = Command()

        # Should not raise exception
        command._schedule_backup_jobs(mock_scheduler)

        # Should still add the job
        mock_scheduler.add_job.assert_called()


@pytest.mark.django_db
@pytest.mark.integration
class TestSchedulerCommand:
    """Tests for the full scheduler Command."""

    def test_handle_sets_up_scheduler(self, temp_backup_dir):
        """handle() should set up scheduler with job store and jobs."""
        PiholeConfigFactory()

        with patch("backup.management.commands.runapscheduler.BlockingScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            # Mock start to exit immediately
            mock_scheduler.start.side_effect = KeyboardInterrupt()

            command = Command()
            command.stdout = MagicMock()

            # Should handle KeyboardInterrupt gracefully
            command.handle()

            # Verify scheduler was configured
            mock_scheduler.add_jobstore.assert_called()
            mock_scheduler.remove_all_jobs.assert_called()

            # Should have added retention and refresh jobs
            job_names = [call.kwargs.get("id") for call in mock_scheduler.add_job.call_args_list]
            assert "retention_cleanup" in job_names
            assert "refresh_schedules" in job_names

    def test_retention_job_scheduled_at_4am(self, temp_backup_dir):
        """Retention job should be scheduled at 4:00 AM."""
        with patch("backup.management.commands.runapscheduler.BlockingScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler
            mock_scheduler.start.side_effect = KeyboardInterrupt()

            command = Command()
            command.stdout = MagicMock()
            command.handle()

            # Find the retention cleanup job call
            for call in mock_scheduler.add_job.call_args_list:
                if call.kwargs.get("id") == "retention_cleanup":
                    trigger = call.kwargs.get("trigger")
                    assert isinstance(trigger, CronTrigger)
                    break

    def test_schedule_refresh_runs_every_5_minutes(self, temp_backup_dir):
        """Schedule refresh should run every 5 minutes."""
        with patch("backup.management.commands.runapscheduler.BlockingScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler
            mock_scheduler.start.side_effect = KeyboardInterrupt()

            command = Command()
            command.stdout = MagicMock()
            command.handle()

            # Find the refresh schedules job call
            for call in mock_scheduler.add_job.call_args_list:
                if call.kwargs.get("id") == "refresh_schedules":
                    trigger = call.kwargs.get("trigger")
                    assert isinstance(trigger, IntervalTrigger)
                    break
