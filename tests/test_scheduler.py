"""Tests for the Scheduler module."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.models import ScheduleConfig, ScheduleFrequency
from src.scheduler import Scheduler


@pytest.fixture
def scheduler(tmp_path):
    """Create a Scheduler with a temp config file."""
    config = ScheduleConfig(
        frequency=ScheduleFrequency.MONTHLY,
        day_of_month=1,
        time="09:00",
        goal="Close out current month",
    )
    return Scheduler(config=config, config_path=tmp_path / "schedule.json")


@pytest.fixture
def weekly_scheduler(tmp_path):
    """Create a weekly scheduler."""
    config = ScheduleConfig(
        frequency=ScheduleFrequency.WEEKLY,
        day_of_week=0,  # Monday
        time="09:00",
        goal="Weekly reconciliation",
    )
    return Scheduler(config=config, config_path=tmp_path / "schedule.json")


@pytest.fixture
def daily_scheduler(tmp_path):
    """Create a daily scheduler."""
    config = ScheduleConfig(
        frequency=ScheduleFrequency.DAILY,
        time="08:00",
        goal="Daily check",
    )
    return Scheduler(config=config, config_path=tmp_path / "schedule.json")


class TestNextRunCalculation:
    """Tests for next run calculation."""

    def test_monthly_next_run(self, scheduler):
        """Should calculate next monthly run."""
        now = datetime(2026, 10, 15, 10, 0)  # Oct 15, past the 1st
        next_run = scheduler.calculate_next_run(now)
        next_dt = datetime.fromisoformat(next_run)
        assert next_dt.day == 1
        assert next_dt.month == 11  # November
        assert next_dt.hour == 9

    def test_monthly_future_this_month(self, scheduler):
        """Should return this month if day hasn't passed yet."""
        now = datetime(2026, 10, 1, 8, 0)  # Oct 1, before 9 AM
        next_run = scheduler.calculate_next_run(now)
        next_dt = datetime.fromisoformat(next_run)
        assert next_dt.day == 1
        assert next_dt.month == 10
        assert next_dt.hour == 9

    def test_monthly_day_15(self, tmp_path):
        """Should handle day_of_month=15."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=15,
            time="10:00",
        )
        sched = Scheduler(config=config, config_path=tmp_path / "schedule.json")
        now = datetime(2026, 10, 10, 12, 0)  # Oct 10
        next_run = sched.calculate_next_run(now)
        next_dt = datetime.fromisoformat(next_run)
        assert next_dt.day == 15
        assert next_dt.month == 10

    def test_monthly_feb_30(self, tmp_path):
        """Should handle Feb 30 by using last day of month."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=30,
            time="09:00",
        )
        sched = Scheduler(config=config, config_path=tmp_path / "schedule.json")
        now = datetime(2026, 2, 1, 10, 0)  # Feb 1
        next_run = sched.calculate_next_run(now)
        next_dt = datetime.fromisoformat(next_run)
        # Feb doesn't have 30 days, should use 28
        assert next_dt.day <= 28
        assert next_dt.month == 2

    def test_weekly_next_run(self, weekly_scheduler):
        """Should calculate next weekly run."""
        # Oct 15, 2026 is a Thursday (weekday=3)
        now = datetime(2026, 10, 15, 10, 0)
        next_run = weekly_scheduler.calculate_next_run(now)
        next_dt = datetime.fromisoformat(next_run)
        assert next_dt.weekday() == 0  # Monday
        assert next_dt > now

    def test_weekly_today_before_time(self, tmp_path):
        """If today is the target day but before time, should run today."""
        # Oct 12, 2026 is a Monday (weekday=0)
        now = datetime(2026, 10, 12, 8, 0)  # Before 9 AM
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=0,
            time="09:00",
        )
        sched = Scheduler(config=config, config_path=tmp_path / "schedule.json")
        next_run = sched.calculate_next_run(now)
        next_dt = datetime.fromisoformat(next_run)
        assert next_dt.day == 12  # Same day
        assert next_dt.hour == 9

    def test_daily_next_run(self, daily_scheduler):
        """Should calculate next daily run."""
        now = datetime(2026, 10, 15, 10, 0)  # Past 8 AM
        next_run = daily_scheduler.calculate_next_run(now)
        next_dt = datetime.fromisoformat(next_run)
        assert next_dt.day == 16  # Tomorrow
        assert next_dt.hour == 8

    def test_daily_today_before_time(self, tmp_path):
        """If before the scheduled time today, should run today."""
        now = datetime(2026, 10, 15, 7, 0)  # Before 8 AM
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time="08:00",
        )
        sched = Scheduler(config=config, config_path=tmp_path / "schedule.json")
        next_run = sched.calculate_next_run(now)
        next_dt = datetime.fromisoformat(next_run)
        assert next_dt.day == 15  # Same day
        assert next_dt.hour == 8

    def test_next_run_stored_in_config(self, scheduler):
        """Should store next_run in config after calculation."""
        scheduler.calculate_next_run()
        assert scheduler.config.next_run is not None


class TestShouldRunNow:
    """Tests for should_run_now check."""

    def test_should_run_when_past(self, scheduler):
        """Should return True when current time is past next_run."""
        # Set next_run to the past
        scheduler.config.next_run = (datetime.now() - timedelta(hours=1)).isoformat()
        assert scheduler.should_run_now() is True

    def test_should_not_run_when_future(self, scheduler):
        """Should return False when next_run is in the future."""
        scheduler.config.next_run = (datetime.now() + timedelta(hours=1)).isoformat()
        assert scheduler.should_run_now() is False

    def test_should_not_run_when_disabled(self, scheduler):
        """Should return False when disabled."""
        scheduler.config.enabled = False
        scheduler.config.next_run = (datetime.now() - timedelta(hours=1)).isoformat()
        assert scheduler.should_run_now() is False

    def test_calculates_next_if_not_set(self, scheduler):
        """Should calculate next_run if not set and return False."""
        scheduler.config.next_run = None
        assert scheduler.should_run_now() is False
        assert scheduler.config.next_run is not None  # Was calculated


class TestExecution:
    """Tests for pipeline execution."""

    def test_execute_updates_last_run(self, scheduler):
        """Execute should update last_run."""
        result = scheduler.execute()
        assert result["status"] == "executed"
        assert scheduler.config.last_run is not None

    def test_execute_calculates_next_run(self, scheduler):
        """Execute should calculate next_run."""
        scheduler.execute()
        assert scheduler.config.next_run is not None

    def test_execute_when_disabled(self, scheduler):
        """Should skip when disabled."""
        scheduler.config.enabled = False
        result = scheduler.execute()
        assert result["status"] == "skipped"

    def test_execute_returns_summary(self, scheduler):
        """Should return execution summary."""
        result = scheduler.execute()
        assert "timestamp" in result
        assert "goal" in result
        assert "frequency" in result
        assert "next_run" in result


class TestManagement:
    """Tests for schedule management."""

    def test_enable(self, scheduler):
        """Should enable the schedule."""
        scheduler.config.enabled = False
        scheduler.enable()
        assert scheduler.config.enabled is True
        assert scheduler.config.next_run is not None

    def test_disable(self, scheduler):
        """Should disable the schedule."""
        scheduler.disable()
        assert scheduler.config.enabled is False

    def test_update_config(self, scheduler):
        """Should update config fields."""
        scheduler.update_config(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=2,
            time="14:00",
            goal="Updated goal",
        )
        assert scheduler.config.frequency == ScheduleFrequency.WEEKLY
        assert scheduler.config.day_of_week == 2
        assert scheduler.config.time == "14:00"
        assert scheduler.config.goal == "Updated goal"

    def test_update_config_recalculates_next(self, scheduler):
        """Updating config should recalculate next_run."""
        scheduler.update_config(time="15:00")
        next_dt = datetime.fromisoformat(scheduler.config.next_run)
        assert next_dt.hour == 15


class TestPersistence:
    """Tests for config persistence."""

    def test_save_creates_file(self, tmp_path):
        """Should create a config file."""
        path = tmp_path / "schedule.json"
        config = ScheduleConfig(goal="Test goal")
        Scheduler(config=config, config_path=path)
        assert path.exists()

    def test_load_existing_file(self, tmp_path):
        """Should load config from existing file."""
        path = tmp_path / "schedule.json"
        config = ScheduleConfig(goal="My goal", time="14:30")
        sched1 = Scheduler(config=config, config_path=path)

        sched2 = Scheduler(config_path=path)
        assert sched2.config.goal == "My goal"
        assert sched2.config.time == "14:30"


class TestFormatting:
    """Tests for output formatting."""

    def test_format_status_enabled(self, scheduler):
        """Should format enabled status."""
        output = scheduler.format_status()
        assert "SCHEDULER STATUS" in output
        assert "ENABLED" in output
        assert "monthly" in output
        assert "09:00" in output

    def test_format_status_disabled(self, scheduler):
        """Should format disabled status."""
        scheduler.config.enabled = False
        output = scheduler.format_status()
        assert "DISABLED" in output

    def test_format_status_weekly(self, weekly_scheduler):
        """Should show day of week for weekly schedule."""
        output = weekly_scheduler.format_status()
        assert "weekly" in output
        assert "Monday" in output

    def test_format_status_has_next_run(self, scheduler):
        """Should show next_run in status."""
        scheduler.calculate_next_run()
        output = scheduler.format_status()
        assert "Next run" in output
        assert scheduler.config.next_run in output


class TestScheduleConfigModel:
    """Tests for the ScheduleConfig model."""

    def test_defaults(self):
        """Should have correct defaults."""
        config = ScheduleConfig()
        assert config.frequency == ScheduleFrequency.MONTHLY
        assert config.day_of_month == 1
        assert config.time == "09:00"
        assert config.enabled is True

    def test_day_of_month_range(self):
        """Should validate day_of_month range."""
        with pytest.raises(Exception):
            ScheduleConfig(day_of_month=32)
        with pytest.raises(Exception):
            ScheduleConfig(day_of_month=0)

    def test_day_of_week_range(self):
        """Should validate day_of_week range."""
        with pytest.raises(Exception):
            ScheduleConfig(day_of_week=7)
        with pytest.raises(Exception):
            ScheduleConfig(day_of_week=-1)
