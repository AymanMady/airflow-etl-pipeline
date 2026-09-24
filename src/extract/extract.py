"""EXTRACT step: reading and validating the source files.

The fundamental rule of extraction: be FAITHFUL TO THE SOURCE.

This step cleans nothing, converts nothing, fixes nothing. All it does is
answer three questions:

    1. Is the file there?
    2. Does it hold the columns the contract promised?
    3. Does it hold at least one row?

If any answer is no, it fails immediately and loudly. That is the **fail fast**
principle: a red pipeline at 01:05 beats a silently wrong dashboard for three
weeks.

Why read everything as text (`dtype=str`)? Because letting pandas guess the
types means invisible decisions: an identifier "007" becomes the integer 7, a
column with a single empty value flips to float, and `NaN` gets mixed in with
strings. Typing is a BUSINESS decision; it belongs to the transformation step.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.config import RAW_DATA_DIR
from src.utils.datasets import DATASETS, DatasetSpec
from src.utils.exceptions import (
    EmptySourceError,
    MissingSourceFileError,
    SchemaValidationError,
)
from src.utils.logging_setup import get_logger

logger = get_logger("EXTRACT")


def _validate_file_exists(path: Path, spec: DatasetSpec) -> None:
    """Check that the source file exists and is readable.

    Raises:
        MissingSourceFileError: the file is missing, or the path points at a
            directory.
    """
    if not path.exists():
        available = (
            sorted(p.name for p in path.parent.glob("*.csv")) if path.parent.exists() else []
        )
        raise MissingSourceFileError(
            f"[{spec.name}] Source file not found: {path}\n"
            f"  Files present in {path.parent}: {available or 'none'}\n"
            f"  Generate the data with: make seed"
        )
    if not path.is_file():
        raise MissingSourceFileError(f"[{spec.name}] {path} is not a file.")


def _validate_columns(frame: pd.DataFrame, spec: DatasetSpec) -> None:
    """Check that every column of the contract is present.

    EXTRA columns are tolerated (a source can evolve and enrich its export
    without breaking our pipeline), but no column may be MISSING.

    Raises:
        SchemaValidationError: at least one required column is missing.
    """
    found = set(frame.columns)
    missing = [column for column in spec.required_columns if column not in found]

    if missing:
        raise SchemaValidationError(
            f"[{spec.name}] Missing columns: {missing}\n"
            f"  Expected: {list(spec.required_columns)}\n"
            f"  Found   : {sorted(found)}"
        )

    extra = found - set(spec.required_columns)
    if extra:
        logger.warning("[%s] Extra columns ignored: %s", spec.name, sorted(extra))


def extract_dataset(spec: DatasetSpec, source_dir: Path | None = None) -> pd.DataFrame:
    """Read and validate a single source file.

    Args:
        spec: the dataset contract (file name, required columns).
        source_dir: folder holding the CSVs. Defaults to `data/raw/`.

    Returns:
        The file contents, every column as raw text.

    Raises:
        MissingSourceFileError: the file is missing.
        SchemaValidationError: the columns do not match.
        EmptySourceError: the file holds no data row at all.
    """
    source_dir = source_dir or RAW_DATA_DIR
    path = source_dir / spec.filename

    logger.info("[EXTRACT] Reading %s", spec.filename)
    _validate_file_exists(path, spec)

    try:
        # keep_default_na=False: "NA", "null", "None" stay STRINGS. Otherwise
        # pandas would silently turn them into NaN, and we would lose the
        # distinction between "missing field" and "field holding the text NA".
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[])
    except pd.errors.EmptyDataError as exc:
        raise EmptySourceError(f"[{spec.name}] Empty file (no header): {path}") from exc
    except pd.errors.ParserError as exc:
        raise SchemaValidationError(f"[{spec.name}] Unreadable CSV: {path} - {exc}") from exc

    _validate_columns(frame, spec)

    if frame.empty:
        raise EmptySourceError(
            f"[{spec.name}] The file holds no row: {path}. "
            "Load interrupted: we refuse to propagate an empty dataset."
        )

    size_kb = path.stat().st_size / 1024
    logger.info(
        "[EXTRACT] %-10s Rows: %-7d Columns: %-2d Size: %.1f KB",
        spec.name,
        len(frame),
        len(frame.columns),
        size_kb,
    )
    return frame


def extract_all(source_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    """Extract the project's three datasets.

    Args:
        source_dir: folder holding the CSVs. Defaults to `data/raw/`.

    Returns:
        A dictionary {dataset_name: DataFrame}.

    Raises:
        PipelineError: on the first invalid source. We do not try to continue
            with a partial set: a half-loaded warehouse is more dangerous than
            one that was never loaded.
    """
    logger.info("=" * 62)
    logger.info("[EXTRACT] Starting - source: %s", source_dir or RAW_DATA_DIR)

    frames = {name: extract_dataset(spec, source_dir) for name, spec in DATASETS.items()}

    total = sum(len(frame) for frame in frames.values())
    logger.info("[EXTRACT] Done - %d datasets, %d rows in total", len(frames), total)
    logger.info("=" * 62)
    return frames
