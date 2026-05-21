"""Daily message scheduling with the schedule library."""

from __future__ import annotations

import logging
import time
from typing import Callable

import schedule

from config import Config

logger = logging.getLogger("identity_agent")


class DailyScheduler:
    """Schedules and runs the identity message job at a fixed time."""

    def __init__(self, config: Config, job: Callable[[], None]) -> None:
        self.config = config
        self.job = job
        self._scheduled = False

    def setup(self) -> None:
        """Register daily job at configured SEND_TIME."""
        send_time = self.config.send_time
        schedule.every().day.at(send_time).do(self._wrapped_job)
        self._scheduled = True
        logger.info("Scheduled daily message at %s", send_time)

    def _wrapped_job(self) -> None:
        """Execute job with error logging."""
        logger.info("Scheduled job triggered")
        try:
            self.job()
        except Exception as e:
            logger.error("Scheduled job failed: %s", e, exc_info=True)

    def run_pending_once(self) -> None:
        """Run job immediately (for testing or --now flag)."""
        logger.info("Running job immediately")
        self._wrapped_job()

    def run_forever(self, poll_interval: float = 30.0) -> None:
        """
        Block and execute pending scheduled jobs.

        Args:
            poll_interval: Seconds between schedule checks.
        """
        if not self._scheduled:
            self.setup()
        logger.info("Scheduler running — press Ctrl+C to stop")
        try:
            while True:
                schedule.run_pending()
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")

    def clear(self) -> None:
        """Remove all scheduled jobs."""
        schedule.clear()
