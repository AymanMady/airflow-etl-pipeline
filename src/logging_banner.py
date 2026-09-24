"""Small helper for formatting the logs."""

from __future__ import annotations

import logging

WIDTH = 62


def banner(logger: logging.Logger, title: str) -> None:
    """Frame a title so the steps stand out visually in the logs."""
    logger.info("=" * WIDTH)
    logger.info("  %s", title)
    logger.info("=" * WIDTH)
