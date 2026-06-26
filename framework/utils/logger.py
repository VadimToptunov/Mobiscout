"""
Structured logging utilities with Rich formatting.
"""

import logging
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

_loggers: dict[str, logging.Logger] = {}
_console = Console(stderr=True)


def setup_logging(
        level: str = "INFO",
        log_file: Optional[Path] = None,
        rich_tracebacks: bool = True,
) -> None:
    """
    Setup logging configuration with Rich handler.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for logging output
        rich_tracebacks: Enable Rich tracebacks for better error display
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=_console,
                rich_tracebacks=rich_tracebacks,
                tracebacks_show_locals=True,
                markup=True,
            )
        ],
    )

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )
        logging.getLogger().addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with the given name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)
    return _loggers[name]
