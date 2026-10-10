"""Scheduler — automates pipeline runs on a recurring schedule.

Supports monthly, weekly, and daily schedules. Calculates the next run time
based on the schedule configuration. Can be triggered via CLI or as a
long-running daemon.

Usage:
    from src.scheduler import Scheduler, ScheduleConfig, ScheduleFrequency

    # Configure monthly run on the 1st at 9 AM
    config = ScheduleConfig(
        frequency=ScheduleFrequency.MONTHLY,
        day_of_month=1,
        time="09:00",
        goal="Close out current month",
    )

    scheduler = Scheduler(config)
    next_run = scheduler.calculate_next_run()
    print(f"Next run: {next_run}")

    # Check if it's time to run
    if scheduler.should_run_now():
        result = scheduler.execute()
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import PROJECT_ROOT
from .models import ScheduleConfig, ScheduleFrequency


class Scheduler:
    """Schedules and executes automated pipeline runs.

    The schedule configuration is persisted to a JSON file so it survives
    across restarts. The actual execution delegates to the Secretary agent.
    """

    def __init__(
        self,
        config: ScheduleConfig | None = None,
        config_path: Path | None = None,
    ):
        """Initialize the scheduler.

        Args:
            config: Schedule configuration. If None, loads from file or defaults.
            config_path: Path for persisting schedule config.
        """
        self.config_path = config_path or (PROJECT_ROOT / "schedule.json")
        self.config = config or self._load_config()
        # If a config was provided, persist it
        if config is not None:
            self._save_config(self.config)

    def _load_config(self) -> ScheduleConfig:
        """Load schedule config from file or create default."""
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                return ScheduleConfig(**data)
            except Exception:
                pass
        # Default: monthly on the 1st at 9 AM
        config = ScheduleConfig()
        self._save_config(config)
        return config

    def _save_config(self, config: ScheduleConfig) -> None:
        """Save schedule config to file."""
        try:
            self.config_path.write_text(
                json.dumps(
                    config.model_dump(),
                    indent=2,
                    default=str,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[Scheduler] Error saving config: {e}")

    # ------------------------------------------------------------------
    # Next run calculation
    # ------------------------------------------------------------------

    def calculate_next_run(self, from_date: datetime | None = None) -> str:
        """Calculate the next scheduled run time.

        Args:
            from_date: Calculate from this datetime. Defaults to now.

        Returns:
            ISO 8601 datetime string for the next run.
        """
        now = from_date or datetime.now()
        freq = self.config.frequency

        if freq == ScheduleFrequency.MONTHLY:
            return self._next_monthly(now)
        elif freq == ScheduleFrequency.WEEKLY:
            return self._next_weekly(now)
        elif freq == ScheduleFrequency.DAILY:
            return self._next_daily(now)
        else:
            return self._next_monthly(now)

    def _next_monthly(self, now: datetime) -> str:
        """Calculate next monthly run."""
        day = self.config.day_of_month or 1
        hour, minute = self._parse_time(self.config.time)

        # Try this month first
        year, month = now.year, now.month
        try:
            candidate = datetime(year, month, day, hour, minute)
        except ValueError:
            # Day doesn't exist in this month (e.g., Feb 30) → use last day
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            candidate = datetime(year, month, min(day, last_day), hour, minute)

        if candidate > now:
            result = candidate
        else:
            # Next month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            try:
                result = datetime(year, month, day, hour, minute)
            except ValueError:
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                result = datetime(year, month, min(day, last_day), hour, minute)

        self.config.next_run = result.isoformat()
        return result.isoformat()

    def _next_weekly(self, now: datetime) -> str:
        """Calculate next weekly run."""
        target_day = self.config.day_of_week or 0  # Monday
        hour, minute = self._parse_time(self.config.time)

        days_ahead = target_day - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now.time() >= self._parse_time_obj(hour, minute)):
            days_ahead += 7

        result = (now + timedelta(days=days_ahead)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        self.config.next_run = result.isoformat()
        return result.isoformat()

    def _next_daily(self, now: datetime) -> str:
        """Calculate next daily run."""
        hour, minute = self._parse_time(self.config.time)

        result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if result <= now:
            result += timedelta(days=1)

        self.config.next_run = result.isoformat()
        return result.isoformat()

    @staticmethod
    def _parse_time(time_str: str) -> tuple[int, int]:
        """Parse HH:MM string to (hour, minute)."""
        try:
            parts = time_str.split(":")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return 9, 0  # Default: 9:00 AM

    @staticmethod
    def _parse_time_obj(hour: int, minute: int):
        """Create a time object."""
        from datetime import time
        return time(hour, minute)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def should_run_now(self) -> bool:
        """Check if the pipeline should run now based on the schedule.

        Returns True if the current time is at or past the next_run time.
        """
        if not self.config.enabled:
            return False

        if not self.config.next_run:
            self.calculate_next_run()
            return False

        try:
            next_dt = datetime.fromisoformat(self.config.next_run)
            return datetime.now() >= next_dt
        except (ValueError, TypeError):
            return False

    def execute(self) -> dict:
        """Execute a scheduled pipeline run.

        This is a stub — in production, it would instantiate the Secretary
        and run the full pipeline. Returns a summary of the run.

        Returns:
            Dict with run summary (timestamp, goal, status).
        """
        if not self.config.enabled:
            return {"status": "skipped", "reason": "Schedule is disabled"}

        now = datetime.now()
        self.config.last_run = now.isoformat()

        # Calculate next run
        self.calculate_next_run(now + timedelta(minutes=1))
        self._save_config(self.config)

        return {
            "status": "executed",
            "timestamp": now.isoformat(),
            "goal": self.config.goal,
            "frequency": self.config.frequency.value,
            "next_run": self.config.next_run,
        }

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def enable(self) -> None:
        """Enable the schedule."""
        self.config.enabled = True
        self.calculate_next_run()
        self._save_config(self.config)

    def disable(self) -> None:
        """Disable the schedule."""
        self.config.enabled = False
        self._save_config(self.config)

    def update_config(self, **kwargs) -> ScheduleConfig:
        """Update schedule configuration.

        Args:
            **kwargs: Fields to update (frequency, day_of_month, time, goal, etc.)

        Returns:
            Updated ScheduleConfig.
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key) and value is not None:
                setattr(self.config, key, value)
        self.calculate_next_run()
        self._save_config(self.config)
        return self.config

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_status(self) -> str:
        """Format the current schedule status as human-readable text."""
        status = "ENABLED" if self.config.enabled else "DISABLED"

        lines = [
            "=" * 60,
            "  SCHEDULER STATUS",
            "=" * 60,
            "",
            f"  Status:       {status}",
            f"  Frequency:    {self.config.frequency.value}",
        ]

        if self.config.frequency == ScheduleFrequency.MONTHLY:
            lines.append(f"  Day of month: {self.config.day_of_month}")
        elif self.config.frequency == ScheduleFrequency.WEEKLY:
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            day_name = days[self.config.day_of_week] if self.config.day_of_week is not None else "Monday"
            lines.append(f"  Day of week:  {day_name}")

        lines.append(f"  Time:         {self.config.time}")
        lines.append(f"  Goal:         {self.config.goal}")
        lines.append(f"  Last run:     {self.config.last_run or '(never)'}")
        lines.append(f"  Next run:     {self.config.next_run or '(not calculated)'}")
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)
