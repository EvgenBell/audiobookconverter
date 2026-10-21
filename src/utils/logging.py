"""
Logging utilities for AudioBookConverter.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# Global logger instance
_logger: Optional[logging.Logger] = None


def setup_logging(
    log_level: int = logging.INFO,
    log_to_file: bool = True,
    log_to_console: bool = False
) -> logging.Logger:
    """
    Set up logging for the application.

    Args:
        log_level: Logging level (default: INFO)
        log_to_file: Whether to log to a file
        log_to_console: Whether to log to console

    Returns:
        Configured logger instance
    """
    global _logger

    if _logger is not None:
        return _logger

    # Create logger
    logger = logging.getLogger("AudioBookConverter")
    logger.setLevel(log_level)

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    if log_to_file:
        from utils.paths import get_log_path, ensure_app_dir

        ensure_app_dir()
        log_path = get_log_path()

        file_handler = logging.FileHandler(
            log_path,
            encoding="utf-8",
            mode="a"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """Get the global logger instance."""
    global _logger

    if _logger is None:
        _logger = setup_logging()

    return _logger


def log_info(message: str) -> None:
    """Log an info message."""
    get_logger().info(message)


def log_warning(message: str) -> None:
    """Log a warning message."""
    get_logger().warning(message)


def log_error(message: str) -> None:
    """Log an error message."""
    get_logger().error(message)


def log_debug(message: str) -> None:
    """Log a debug message."""
    get_logger().debug(message)


def log_exception(message: str, exc: Optional[Exception] = None) -> None:
    """Log an exception with traceback."""
    if exc:
        get_logger().exception(message, exc_info=exc)
    else:
        get_logger().exception(message)


class LogBuffer(logging.Handler):
    """
    A logging handler that stores messages in memory for UI display.
    """

    def __init__(self, max_records: int = 1000):
        super().__init__()
        self.max_records = max_records
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Store a log record."""
        if len(self.records) >= self.max_records:
            self.records.pop(0)

        self.records.append({
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": self.format(record)
        })

    def get_records(self, level: Optional[str] = None) -> list[dict]:
        """Get all records, optionally filtered by level."""
        if level:
            return [r for r in self.records if r["level"] == level]
        return self.records.copy()

    def clear(self) -> None:
        """Clear all records."""
        self.records.clear()

    def get_last_errors(self, count: int = 10) -> list[str]:
        """Get the last N error messages."""
        errors = [r["message"] for r in self.records if r["level"] == "ERROR"]
        return errors[-count:]
