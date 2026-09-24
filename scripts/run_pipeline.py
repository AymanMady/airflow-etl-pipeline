#!/usr/bin/env python3
"""Run the full ETL pipeline outside Airflow.

Useful for developing and debugging without waiting for the scheduler to fire,
and for demonstrating idempotency by running it twice in a row.

Usage:
    make run-local           # through the Makefile (recommended)
    python scripts/run_pipeline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extract.extract import extract_all  # noqa: E402
from src.load.load import load_all  # noqa: E402
from src.logging_banner import banner  # noqa: E402
from src.transform.transform import transform_all  # noqa: E402
from src.utils.exceptions import PipelineError  # noqa: E402
from src.utils.logging_setup import get_logger  # noqa: E402

logger = get_logger("PIPELINE")


def main() -> int:
    """Chain extract -> transform -> load.

    Returns:
        0 if everything went well, 1 on a business error of the pipeline.
    """
    banner(logger, "E-COMMERCE ETL PIPELINE")
    try:
        raw_frames = extract_all()
        clean_frames, _ = transform_all(raw_frames)
        stats = load_all(clean_frames)
    except PipelineError as exc:
        # We only catch OUR exceptions: an unexpected error must bubble up
        # with its full stack trace so it can be diagnosed.
        logger.error("[PIPELINE] FAILED - %s", exc)
        return 1

    banner(logger, "SUMMARY")
    for dataset, counters in stats.items():
        logger.info(
            "  %-10s inserted=%-6d updated=%-6d",
            dataset,
            counters["inserted"],
            counters["updated"],
        )
    logger.info("[PIPELINE] SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
