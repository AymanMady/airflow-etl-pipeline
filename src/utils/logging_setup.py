"""Uniform logging for every step of the pipeline.

Airflow automatically captures anything that goes through the standard
`logging` module and attaches it to the relevant task instance. That is why the
code never uses `print()`: a print is not timestamped, cannot be filtered by
level, and gets lost in the aggregated logs.
"""

from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """Return a ready-to-use logger.

    Args:
        name: the logger name, typically the step name ("EXTRACT").

    Returns:
        A logger writing to stdout, with no duplicated handler.
    """
    logger = logging.getLogger(name)

    # Under Airflow, handlers are already installed: we do not add more, or
    # every line would show up twice in the logs.
    if not logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger
