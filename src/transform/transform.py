"""TRANSFORM step: cleaning and business validation.

Extraction brought the data back as it was. This step makes it USABLE, by
applying explicit rules:

    - removing duplicates
    - normalising text (whitespace, casing)
    - normalising emails, setting them to NULL when invalid
    - converting types (identifiers, prices, quantities)
    - normalising dates, whatever their original format
    - rejecting the rows that violate a blocking business rule

There are two ways to handle an anomaly, and the choice is never trivial:

    FIX      when the information stays usable without the offending field.
             A customer with an invalid email is still a customer: we clear
             the email and keep the customer.

    REJECT   when the row becomes unusable. An order with no valid quantity
             cannot contribute to revenue: keeping it would distort every
             aggregate.

Rejected rows do not vanish: they are written to
`data/processed/rejected_*.csv`. That is the **quarantine**. Dropping data
silently is one of the gravest faults in data engineering - the day the
business asks "why did revenue drop?", you have to be able to show exactly
what was set aside, and why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.utils.config import PROCESSED_DATA_DIR
from src.utils.datasets import CUSTOMERS, ORDERS, PRODUCTS, VALID_ORDER_STATUSES
from src.utils.logging_setup import get_logger

logger = get_logger("TRANSFORM")

#: Accepted date formats, tried IN THIS ORDER.
#: We never let pandas "guess": on a mixed set it may read 03/04/2026 as
#: 3 April on one row and 4 March on the next.
DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y")

#: A valid email: some text, an @, a domain, a dot, an extension.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


@dataclass
class TransformReport:
    """Numbers summarising the cleaning of one dataset.

    Making these figures explicit means they can be logged, tested, and one day
    stored over time to detect drift (for example: the rejection rate jumping
    from 2% to 40% overnight).
    """

    dataset: str
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    nulls_found: int = 0
    rejected: dict[str, int] = field(default_factory=dict)

    @property
    def rows_removed(self) -> int:
        return self.rows_in - self.rows_out

    def reject(self, reason: str, count: int) -> None:
        """Record a rejection reason (ignored when no row is affected)."""
        if count:
            self.rejected[reason] = self.rejected.get(reason, 0) + count

    def log(self) -> None:
        """Write the summary to the logs, in a format readable at a glance."""
        logger.info("[TRANSFORM] Cleaning %s", self.dataset)
        logger.info("[TRANSFORM]   Rows before   : %d", self.rows_in)
        logger.info("[TRANSFORM]   Rows after    : %d", self.rows_out)
        logger.info("[TRANSFORM]   Rows removed  : %d", self.rows_removed)
        logger.info("[TRANSFORM]   Null values   : %d", self.nulls_found)
        logger.info("[TRANSFORM]   Duplicates    : %d", self.duplicates_removed)
        for reason, count in sorted(self.rejected.items(), key=lambda kv: -kv[1]):
            logger.info("[TRANSFORM]     rejected - %-28s %d", reason, count)


# -----------------------------------------------------------------------------
#  Helper functions, shared by the three datasets
# -----------------------------------------------------------------------------
def _blank_to_na(frame: pd.DataFrame) -> pd.DataFrame:
    """Turn empty strings and whitespace-only values into missing values.

    CSV makes no difference between "missing field" and "empty string": both
    are written `,,`. We settle it here, once and for all.
    """
    return frame.replace(r"^\s*$", pd.NA, regex=True)


def _strip_text(series: pd.Series) -> pd.Series:
    """Strip the edge whitespace and collapse the internal whitespace."""
    return series.str.strip().str.replace(r"\s+", " ", regex=True)


def _titlecase(series: pd.Series) -> pd.Series:
    """Normalise the casing: "  FRANCE " and "france" both become "France"."""
    return _strip_text(series).str.title()


def _normalize_email(series: pd.Series) -> pd.Series:
    """Normalise the emails and replace the invalid ones with a missing value.

    A deliberate choice: we do NOT DROP the customer. A customer with no email
    is still a valid customer when analysing revenue by country.
    """
    cleaned = series.str.strip().str.lower()
    valid = cleaned.str.match(EMAIL_PATTERN, na=False)
    return cleaned.where(valid, pd.NA)


def _parse_dates(series: pd.Series) -> pd.Series:
    """Convert a text column into dates, trying several formats.

    Each format is only tried on the rows that are still unresolved. Values no
    format can parse become NaT (Not a Time).
    """
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for date_format in DATE_FORMATS:
        pending = result.isna() & series.notna()
        if not pending.any():
            break
        result.loc[pending] = pd.to_datetime(series[pending], format=date_format, errors="coerce")
    return result


def _to_numeric(series: pd.Series, as_integer: bool = False) -> pd.Series:
    """Convert to a number; whatever cannot be converted becomes missing.

    `Int64` (capitalised) is pandas' NULLABLE integer type: it can represent a
    missing integer, which the plain `int` cannot - it falls back to float, and
    42 becomes 42.0.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.astype("Int64") if as_integer else numeric


def _drop_duplicates(frame: pd.DataFrame, key: str, report: TransformReport) -> pd.DataFrame:
    """Drop primary-key duplicates, keeping the first occurrence.

    We deduplicate on the KEY, not on the whole row: two rows sharing an
    identifier but differing in one field are still a business duplicate, and
    letting both through would blow up the load (key violation).
    """
    before = len(frame)
    deduplicated = frame.drop_duplicates(subset=[key], keep="first")
    report.duplicates_removed = before - len(deduplicated)
    return deduplicated


def _require(
    frame: pd.DataFrame, mask: pd.Series, reason: str, report: TransformReport
) -> pd.DataFrame:
    """Keep the rows satisfying `mask`, count and quarantine the rest.

    Args:
        mask: the condition to satisfy. `True` = the row is kept.
        reason: readable reason, logged and written to the rejects file.
    """
    mask = mask.fillna(False)
    rejected = frame[~mask]
    if not rejected.empty:
        report.reject(reason, len(rejected))
        _quarantine(rejected, report.dataset, reason)
    return frame[mask]


_QUARANTINE_BUFFER: dict[str, list[pd.DataFrame]] = {}


def _quarantine(rows: pd.DataFrame, dataset: str, reason: str) -> None:
    """Set the rejected rows aside, along with their reason."""
    tagged = rows.copy()
    tagged["_rejection_reason"] = reason
    _QUARANTINE_BUFFER.setdefault(dataset, []).append(tagged)


def flush_quarantine(output_dir: Path | None = None) -> dict[str, Path]:
    """Write the rejected rows to disk and empty the buffer.

    Returns:
        A dictionary {dataset: path of the rejects file}.
    """
    output_dir = output_dir or PROCESSED_DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    for dataset, chunks in _QUARANTINE_BUFFER.items():
        path = output_dir / f"rejected_{dataset}.csv"
        pd.concat(chunks, ignore_index=True).to_csv(path, index=False)
        written[dataset] = path
        logger.info("[TRANSFORM] Quarantine: %s", path)

    _QUARANTINE_BUFFER.clear()
    return written


# -----------------------------------------------------------------------------
#  Per-dataset transformations
# -----------------------------------------------------------------------------
def transform_customers(frame: pd.DataFrame) -> tuple[pd.DataFrame, TransformReport]:
    """Clean the customers table.

    Rules:
        - identifier mandatory and integer       -> reject otherwise
        - creation date mandatory and parsable   -> reject otherwise
        - email normalised, cleared if invalid   -> fix
        - names and country: whitespace, casing  -> fix
    """
    report = TransformReport(dataset=CUSTOMERS.name, rows_in=len(frame))
    frame = _blank_to_na(frame.copy())
    report.nulls_found = int(frame.isna().sum().sum())

    frame["customer_id"] = _to_numeric(frame["customer_id"], as_integer=True)
    frame["first_name"] = _titlecase(frame["first_name"])
    frame["last_name"] = _titlecase(frame["last_name"])
    frame["country"] = _titlecase(frame["country"])
    frame["email"] = _normalize_email(frame["email"])
    frame["created_at"] = _parse_dates(frame["created_at"])

    frame = _require(frame, frame["customer_id"].notna(), "customer_id missing", report)
    frame = _require(frame, frame["created_at"].notna(), "created_at not parsable", report)
    frame = _drop_duplicates(frame, CUSTOMERS.primary_key, report)

    frame = frame[list(CUSTOMERS.required_columns)].reset_index(drop=True)
    report.rows_out = len(frame)
    report.log()
    return frame, report


def transform_products(frame: pd.DataFrame) -> tuple[pd.DataFrame, TransformReport]:
    """Clean the product catalogue.

    Rules:
        - identifier mandatory and integer -> reject otherwise
        - name mandatory                   -> reject otherwise
        - price present and >= 0           -> reject otherwise

    Why reject a product with no price rather than setting it to 0? Because a
    price of 0 propagates silently into revenue and drags it down without
    anyone understanding why. A missing product, on the other hand, is visible.
    """
    report = TransformReport(dataset=PRODUCTS.name, rows_in=len(frame))
    frame = _blank_to_na(frame.copy())
    report.nulls_found = int(frame.isna().sum().sum())

    frame["product_id"] = _to_numeric(frame["product_id"], as_integer=True)
    frame["product_name"] = _strip_text(frame["product_name"])
    frame["category"] = _titlecase(frame["category"])
    frame["price"] = _to_numeric(frame["price"]).round(2)

    frame = _require(frame, frame["product_id"].notna(), "product_id missing", report)
    frame = _require(frame, frame["product_name"].notna(), "product_name missing", report)
    frame = _require(frame, frame["price"].notna(), "price missing or not numeric", report)
    frame = _require(frame, frame["price"] >= 0, "price negative", report)
    frame = _drop_duplicates(frame, PRODUCTS.primary_key, report)

    frame = frame[list(PRODUCTS.required_columns)].reset_index(drop=True)
    report.rows_out = len(frame)
    report.log()
    return frame, report


def transform_orders(frame: pd.DataFrame) -> tuple[pd.DataFrame, TransformReport]:
    """Clean the orders.

    Rules:
        - identifiers mandatory and integer  -> reject otherwise
        - integer quantity strictly > 0      -> reject otherwise
        - parsable order date                -> reject otherwise
        - status lowercased, then belonging to the reference list
                                             -> reject otherwise

    Note: orders referencing a non-existent customer or product are NOT
    rejected here. The `raw` layer stays faithful to the source; dbt is what
    detects those orphans, with a `relationships` test (PHASE 8). Mixing the
    two responsibilities would make the anomaly invisible.
    """
    report = TransformReport(dataset=ORDERS.name, rows_in=len(frame))
    frame = _blank_to_na(frame.copy())
    report.nulls_found = int(frame.isna().sum().sum())

    for column in ("order_id", "customer_id", "product_id", "quantity"):
        frame[column] = _to_numeric(frame[column], as_integer=True)
    frame["order_date"] = _parse_dates(frame["order_date"])
    # "PAID" and "Shipped" are casing mistakes, not unknown statuses: we
    # recover them before judging their validity.
    frame["status"] = frame["status"].str.strip().str.lower()

    frame = _require(frame, frame["order_id"].notna(), "order_id missing", report)
    frame = _require(frame, frame["customer_id"].notna(), "customer_id missing", report)
    frame = _require(frame, frame["product_id"].notna(), "product_id missing", report)
    frame = _require(frame, frame["quantity"].notna(), "quantity missing", report)
    frame = _require(frame, frame["quantity"] > 0, "quantity <= 0", report)
    frame = _require(frame, frame["order_date"].notna(), "order_date not parsable", report)
    frame = _require(
        frame, frame["status"].isin(VALID_ORDER_STATUSES), "status outside reference list", report
    )
    frame = _drop_duplicates(frame, ORDERS.primary_key, report)

    frame = frame[list(ORDERS.required_columns)].reset_index(drop=True)
    report.rows_out = len(frame)
    report.log()
    return frame, report


#: Dispatch table: each dataset gets its cleaning function.
TRANSFORMERS = {
    CUSTOMERS.name: transform_customers,
    PRODUCTS.name: transform_products,
    ORDERS.name: transform_orders,
}


def transform_all(
    frames: dict[str, pd.DataFrame], output_dir: Path | None = None
) -> tuple[dict[str, pd.DataFrame], dict[str, TransformReport]]:
    """Apply the cleaning to the three datasets.

    Args:
        frames: the output of `extract_all()`.
        output_dir: destination of the quarantine files.

    Returns:
        The cleaned DataFrames, and the report for each dataset.
    """
    logger.info("=" * 62)
    logger.info("[TRANSFORM] Starting")

    cleaned: dict[str, pd.DataFrame] = {}
    reports: dict[str, TransformReport] = {}

    for name, frame in frames.items():
        cleaned[name], reports[name] = TRANSFORMERS[name](frame)

    flush_quarantine(output_dir)

    total_in = sum(r.rows_in for r in reports.values())
    total_out = sum(r.rows_out for r in reports.values())
    logger.info(
        "[TRANSFORM] Done - %d rows in, %d kept (%.1f%% rejected)",
        total_in,
        total_out,
        100 * (total_in - total_out) / total_in if total_in else 0,
    )
    logger.info("=" * 62)
    return cleaned, reports
