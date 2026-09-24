"""LOAD step: idempotent loading into PostgreSQL.

    IDEMPOTENCY: running the operation once or ten times produces exactly the
    same final state.

This is THE property that separates a production pipeline from a script.

Without it:

    Run 1 (01:00) ............. 100 orders inserted
    Run 2 (rerun after a bug) . 100 orders inserted again
    Result .................... 200 rows, revenue doubled

With it:

    Run 1 ..................... 100 orders inserted
    Run 2 ..................... 100 orders updated
    Result .................... 100 rows. Always.

This is not a theoretical detail. A pipeline is rerun all the time: after a
network failure, after an automatic retry, during a backfill over thirty days
of history, or because a colleague clicked "Clear" in the Airflow UI. If every
rerun duplicates the data, you can never rerun again - so you can never repair
anything again.

**How we get it here**: a primary key + `INSERT ... ON CONFLICT DO UPDATE`,
PostgreSQL's UPSERT. The primary key identifies the row; on a collision,
PostgreSQL updates instead of failing.

**The other possible strategies**, worth knowing they exist:

    TRUNCATE + INSERT   simple, but the table is empty during the load and the
                        history is lost on every run.
    DELETE + INSERT     by date partition: well suited to a daily incremental
                        load (see V2).
    MERGE               the standard SQL equivalent, available since PG 15.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import connection as PgConnection  # noqa: N812
from psycopg2.extras import execute_values

from src.utils.config import PostgresConfig
from src.utils.datasets import DATASETS, DatasetSpec
from src.utils.exceptions import LoadError
from src.utils.logging_setup import get_logger

logger = get_logger("LOAD")

SCHEMA = "raw"
DDL_PATH = Path(__file__).parent / "sql" / "raw_tables.sql"

#: Rows sent per query. Too small = too many network round trips; too large =
#: a memory spike. 1000 is a good compromise.
BATCH_SIZE = 1000


def get_connection(config: PostgresConfig | None = None) -> PgConnection:
    """Open a connection to the warehouse.

    Raises:
        LoadError: the database is unreachable. Unlike data errors, this one IS
            retryable: an unavailable database becomes available again.
    """
    config = config or PostgresConfig.from_env()
    try:
        return psycopg2.connect(config.dsn)
    except psycopg2.OperationalError as exc:
        raise LoadError(
            f"Cannot connect to the warehouse ({config!r}): {exc}\n"
            "  Check that the containers are running: make ps"
        ) from exc


def ensure_schema(conn: PgConnection) -> None:
    """Create the `raw` layer tables if they do not exist."""
    logger.info("[LOAD] Checking schema %s", SCHEMA)
    with conn.cursor() as cursor:
        cursor.execute(DDL_PATH.read_text(encoding="utf-8"))
    conn.commit()


def _to_records(frame: pd.DataFrame, columns: list[str]) -> list[tuple]:
    """Convert a DataFrame into rows psycopg2 accepts.

    pandas' missing values (`NA`, `NaT`, `NaN`) mean nothing to the PostgreSQL
    driver: they have to become `None`, which turns into NULL in SQL. Without
    this step the database would receive the string "NaT" in a timestamp
    column.
    """
    prepared = frame[columns].astype(object).where(pd.notna(frame[columns]), None)
    return list(prepared.itertuples(index=False, name=None))


def _count_rows(conn: PgConnection, table: str) -> int:
    """Count the rows of a table."""
    with conn.cursor() as cursor:
        cursor.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(SCHEMA), sql.Identifier(table)
            )
        )
        return cursor.fetchone()[0]


def _build_upsert(spec: DatasetSpec, columns: list[str]) -> sql.Composed:
    """Build the UPSERT query for a dataset.

    The query produced looks like:

        INSERT INTO raw.orders (order_id, customer_id, ...)
        VALUES %s
        ON CONFLICT (order_id) DO UPDATE SET
            customer_id = EXCLUDED.customer_id,
            ...,
            _loaded_at  = now();

    `EXCLUDED` is a PostgreSQL pseudo-table holding the row we tried to insert.
    So we are saying: "on a collision on the key, replace the old values with
    the new ones".

    We use `psycopg2.sql` rather than f-strings: identifiers are escaped
    properly, which closes the door on SQL injection.
    """
    updatable = [column for column in columns if column != spec.primary_key]

    return sql.SQL(
        "INSERT INTO {schema}.{table} ({columns}) VALUES %s "
        "ON CONFLICT ({pkey}) DO UPDATE SET {assignments}, _loaded_at = now()"
    ).format(
        schema=sql.Identifier(SCHEMA),
        table=sql.Identifier(spec.name),
        columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
        pkey=sql.Identifier(spec.primary_key),
        assignments=sql.SQL(", ").join(
            sql.SQL("{col} = EXCLUDED.{col}").format(col=sql.Identifier(column))
            for column in updatable
        ),
    )


def load_dataset(conn: PgConnection, spec: DatasetSpec, frame: pd.DataFrame) -> dict[str, int]:
    """Load a dataset idempotently.

    Args:
        conn: an open connection to the warehouse.
        spec: the dataset contract (table name, primary key).
        frame: the data cleaned by the transform step.

    Returns:
        {"processed": rows sent, "inserted": new ones, "updated": existing ones}

    Raises:
        LoadError: any database error. The transaction is rolled back: the
            table stays as it was before the load, never half filled.
    """
    columns = list(spec.required_columns)
    records = _to_records(frame, columns)

    logger.info("[LOAD] Loading %s into PostgreSQL (%d rows)", spec.name, len(records))
    before = _count_rows(conn, spec.name)

    try:
        with conn.cursor() as cursor:
            execute_values(cursor, _build_upsert(spec, columns), records, page_size=BATCH_SIZE)
        # A single commit for the whole dataset: either the entire table is up
        # to date, or nothing moves. That is atomicity (the "A" in ACID).
        conn.commit()
    except psycopg2.Error as exc:
        conn.rollback()
        raise LoadError(
            f"[{spec.name}] Load failed: {exc}\n"
            "  The transaction was rolled back, the table is intact."
        ) from exc

    after = _count_rows(conn, spec.name)
    inserted = after - before
    stats = {
        "processed": len(records),
        "inserted": inserted,
        "updated": len(records) - inserted,
    }
    logger.info(
        "[LOAD] %-10s processed=%-6d inserted=%-6d updated=%-6d total_in_table=%d",
        spec.name,
        stats["processed"],
        stats["inserted"],
        stats["updated"],
        after,
    )
    return stats


def load_all(
    frames: dict[str, pd.DataFrame], config: PostgresConfig | None = None
) -> dict[str, dict[str, int]]:
    """Load the three datasets into the warehouse.

    The order follows `DATASETS`: customers and products first, orders next. It
    is not enforced by foreign keys (there are none in `raw`), but it keeps the
    warehouse coherent at any moment for a reader.

    Returns:
        The load statistics per dataset.
    """
    logger.info("=" * 62)
    logger.info("[LOAD] Starting")

    conn = get_connection(config)
    try:
        ensure_schema(conn)
        stats = {
            name: load_dataset(conn, spec, frames[name])
            for name, spec in DATASETS.items()
            if name in frames
        }
    finally:
        # `finally` guarantees the close even if an exception was raised: a
        # forgotten connection holds a server-side slot until it times out.
        conn.close()

    total = sum(s["processed"] for s in stats.values())
    logger.info("[LOAD] Done - %d rows processed", total)
    logger.info("=" * 62)
    return stats
