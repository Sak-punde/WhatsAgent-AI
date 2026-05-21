"""Premium terminal and file logging configuration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from colorama import Fore, Style, init

init(autoreset=True)


class PremiumFormatter(logging.Formatter):
    """Colorful console formatter with timestamps and level tags."""

    LEVEL_STYLES: dict[int, tuple[str, str]] = {
        logging.DEBUG: (Fore.CYAN, "DEBUG"),
        logging.INFO: (Fore.GREEN, "INFO "),
        logging.WARNING: (Fore.YELLOW, "WARN "),
        logging.ERROR: (Fore.RED, "ERROR"),
    }

    SUCCESS_LEVEL = 25  # Between INFO and WARNING

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for terminal display."""
        if record.levelno == self.SUCCESS_LEVEL:
            color, tag = Fore.GREEN, "OK   "
        else:
            color, tag = self.LEVEL_STYLES.get(
                record.levelno, (Fore.WHITE, "LOG  ")
            )

        timestamp = self.formatTime(record, "%H:%M:%S")
        message = record.getMessage()

        return (
            f"{Fore.WHITE}[{timestamp}] {tag} {color}{message}{Style.RESET_ALL}"
        )


class FileFormatter(logging.Formatter):
    """Plain formatter for log files."""

    def format(self, record: logging.LogRecord) -> str:
        return (
            f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} "
            f"[{record.levelname}] {record.getMessage()}"
        )


def setup_logging(logs_dir: Path, log_name: str = "app.log") -> logging.Logger:
    """
    Configure root logger with console and file handlers.

    Args:
        logs_dir: Directory for log files.
        log_name: Log file name.

    Returns:
        Configured logger instance.
    """
    logging.addLevelName(PremiumFormatter.SUCCESS_LEVEL, "SUCCESS")

    def success(self: logging.Logger, msg: str, *args: object, **kwargs: object) -> None:
        if self.isEnabledFor(PremiumFormatter.SUCCESS_LEVEL):
            self._log(PremiumFormatter.SUCCESS_LEVEL, msg, args, **kwargs)

    logging.Logger.success = success  # type: ignore[method-assign]

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / log_name

    logger = logging.getLogger("identity_agent")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(PremiumFormatter())
    logger.addHandler(console)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(FileFormatter())
    logger.addHandler(file_handler)

    return logger
