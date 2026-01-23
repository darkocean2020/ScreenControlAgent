"""Logging utilities for ScreenControlAgent."""

import logging
import sys
from pathlib import Path
from typing import Optional


_logger_initialized = False


def setup_logger(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> None:
    """
    Setup the root logger for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for logging
        format_string: Optional custom format string
    """
    global _logger_initialized

    if _logger_initialized:
        return

    log_format = format_string or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    root_logger = logging.getLogger("screen_agent")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if root_logger.handlers:
        root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(log_format))
        root_logger.addHandler(file_handler)

    _logger_initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    if not _logger_initialized:
        setup_logger()

    if name.startswith("screen_agent"):
        return logging.getLogger(name)
    return logging.getLogger(f"screen_agent.{name}")
