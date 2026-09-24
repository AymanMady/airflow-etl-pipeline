"""Main DAG: the daily e-commerce ETL pipeline.

This file is where the business code (`src/`) meets the orchestrator. It holds
NO processing logic: all it does is declare which steps exist, in what order,
and under what failure conditions.

That separation is deliberate and important:

    src/     business logic - testable with pytest, without Airflow
    dags/    orchestration  - what, when, in which order

If all the logic lived in the DAG, it could only be tested by starting Airflow,
and it could no longer be reused anywhere else.

--------------------------------------------------------------------------
 Why the tasks exchange PATHS and not data
--------------------------------------------------------------------------
Each Airflow task runs in its own process: Python variables do not survive from
one task to the next. The exchange mechanism is called **XCom**
(cross-communication), and whatever a task returns is stored there.

But XCom writes into the metadata database. Passing a 5,000-row DataFrame
through it would be a mistake:

    - the metadata database is not meant to store business data;
    - the content has to be JSON-serialisable - a DataFrame is not;
    - the database grows on every run and ends up slowing all of Airflow down.

The rule: **XCom carries references and metrics, never data.** Here, each task
writes its result as Parquet on the shared disk and only passes the path along
with a few counters.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

from src.extract.extract import extract_all
from src.load.load import load_all
from src.transform.transform import transform_all
from src.utils.config import PROCESSED_DATA_DIR
from src.utils.logging_setup import get_logger

logger = get_logger("DAG")

# -----------------------------------------------------------------------------
#  dbt
# -----------------------------------------------------------------------------
#  dbt lives in its own virtual environment (see docker/airflow/Dockerfile).
#  We invoke it by absolute path: no dependency is shared with Airflow, so no
#  version conflict is possible.
DBT_BIN = "/opt/dbt_venv/bin/dbt"
DBT_PROJECT_DIR = "/opt/airflow/dbt/ecommerce_dbt"

# -----------------------------------------------------------------------------
#  Default parameters applied to EVERY task of the DAG
# -----------------------------------------------------------------------------
#  These values apply to each task unless explicitly overridden.
DEFAULT_ARGS = {
    "owner": "data-engineering",
    # --- depends_on_past ---
    #  False: the 16 September run does not depend on the 15th's. A single
    #  failure therefore does not block every following day. We would switch to
    #  True for a cumulative computation, where chronological order is
    #  mandatory.
    "depends_on_past": False,
    # --- RETRIES ---
    #  Airflow automatically reruns a failed task, twice, five minutes apart.
    #  Why that helps: a good share of production failures are TRANSIENT - a
    #  one-second network outage, a database restarting, a momentary lock, an
    #  API quota hit. Without retries, a 10-second incident at 01:00 turns into
    #  a day of missing data nobody notices until tomorrow.
    #
    #  What DESERVES a retry:
    #      network error, database unavailable, connection timeout,
    #      concurrent lock, a third-party service momentarily saturated.
    #
    #  What MUST NOT be retried:
    #      missing source file, missing column, invalid data, SQL syntax error,
    #      a bug in the code.
    #      Rerunning a bug three times only delays the alert by 10 minutes and
    #      bloats the logs. That is why the pipeline's exceptions
    #      (src/utils/exceptions.py) document, one by one, whether they are
    #      retryable.
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    # --- TIMEOUT ---
    #  With no time limit, a stuck task never fails: it stays "running"
    #  indefinitely, holds an execution slot, blocks the next run
    #  (max_active_runs=1) and alerts nobody - because from Airflow's point of
    #  view everything is fine.
    #
    #  The classic case: a SQL query waiting on a lock that is never released.
    #  It will wait for days. With a timeout the task fails, the retry fires,
    #  and the alert goes out.
    #
    #  Rule of thumb: 3 to 5 times the normal observed duration. Too short and
    #  you kill healthy runs on heavy days; too long and the guard rail loses
    #  its point.
    "execution_timeout": timedelta(minutes=20),
}


def _partition_dir(partition: str, stage: str) -> Path:
    """Working directory of a run, isolated by logical date.

    Each run writes into its own `data/processed/<date>/` folder. A backfill of
    15 September therefore does not overwrite the 16th's work, and replaying
    the same date rewrites exactly the same files: that is what makes the
    intermediate steps idempotent too.
    """
    path = PROCESSED_DATA_DIR / partition / stage
    path.mkdir(parents=True, exist_ok=True)
    return path


@dag(
    dag_id="ecommerce_daily_etl",
    description="E-commerce ETL pipeline: CSV -> PostgreSQL -> dbt -> quality tests",
    # --- SCHEDULING ---
    #  Cron expression: minute hour day month weekday
    #  "0 1 * * *" = every day at 01:00 UTC.
    schedule="0 1 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=False,
    # One run at a time: two simultaneous runs would write into the same
    # tables and step on each other.
    max_active_runs=1,
    # Global guard rail: beyond this, the whole run is marked as failed.
    dagrun_timeout=timedelta(hours=1),
    default_args=DEFAULT_ARGS,
    tags=["ecommerce", "etl", "portfolio"],
    doc_md=__doc__,
)
def ecommerce_daily_etl():
    """Pipeline definition. Each decorated function is a TASK."""

    @task
    def extract_data(partition: str) -> dict[str, str]:
        """Read and validate the source CSVs.

        Args:
            partition: the run's logical date (`{{ ds }}`), in YYYY-MM-DD
                format. Airflow substitutes it before the call.

        Returns:
            {dataset: path of the extracted Parquet} - travels through XCom.
        """
        frames = extract_all()
        target = _partition_dir(partition, "extracted")

        paths: dict[str, str] = {}
        for name, frame in frames.items():
            path = target / f"{name}.parquet"
            frame.to_parquet(path, index=False)
            paths[name] = str(path)
            logger.info("[EXTRACT] %s -> %s (%d rows)", name, path, len(frame))
        return paths

    @task
    def transform_data(paths: dict[str, str], partition: str) -> dict[str, str]:
        """Clean and validate the extracted data.

        Args:
            paths: the output of `extract_data`, retrieved through XCom.
            partition: the run's logical date.

        Returns:
            {dataset: path of the cleaned Parquet}.
        """
        import pandas as pd

        frames = {name: pd.read_parquet(path) for name, path in paths.items()}
        cleaned, reports = transform_all(frames)
        target = _partition_dir(partition, "transformed")

        output: dict[str, str] = {}
        for name, frame in cleaned.items():
            path = target / f"{name}.parquet"
            frame.to_parquet(path, index=False)
            output[name] = str(path)

        # An abnormal rejection rate is a signal: we make it visible in the
        # logs even when the pipeline succeeds.
        for name, report in reports.items():
            if report.rows_in and report.rows_removed / report.rows_in > 0.25:
                logger.warning(
                    "[TRANSFORM] %s: %.1f%% of the rows rejected - check the source",
                    name,
                    100 * report.rows_removed / report.rows_in,
                )
        return output

    @task
    def load_data(paths: dict[str, str]) -> dict[str, int]:
        """Load the cleaned data into PostgreSQL (idempotent UPSERT).

        Args:
            paths: the output of `transform_data`.

        Returns:
            The number of rows processed per dataset.
        """
        import pandas as pd

        frames = {name: pd.read_parquet(path) for name, path in paths.items()}
        stats = load_all(frames)

        for name, counters in stats.items():
            logger.info(
                "[LOAD] %-10s inserted=%d updated=%d",
                name,
                counters["inserted"],
                counters["updated"],
            )
        return {name: counters["processed"] for name, counters in stats.items()}

    # -------------------------------------------------------------------------
    #  dbt TASKS
    # -------------------------------------------------------------------------
    #  Here we use a BashOperator rather than the TaskFlow API: dbt is an
    #  external executable, not a Python function. This is the right tool to run
    #  a command.
    #
    #  `dbt run` builds the models. It reads the raw layer load_data has just
    #  filled and rebuilds staging, then analytics.
    run_dbt = BashOperator(
        task_id="run_dbt",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && {DBT_BIN} run --profiles-dir {DBT_PROJECT_DIR} --target dev"
        ),
        execution_timeout=timedelta(minutes=30),
        doc_md="""
        Builds the dbt models: 3 staging views, 4 analytical tables.

        dbt works out the execution order on its own, from the `ref()` calls in
        the SQL. We never hand it a sequence.
        """,
    )

    #  `dbt test` runs the 60 quality tests. The exit code decides the task's
    #  fate:
    #      0  everything passes, or only warnings  -> green task
    #      1  at least one test in `error`         -> RED task
    #
    #  That is what makes quality BLOCKING: as soon as a critical rule is
    #  violated, the DAG fails and the alert goes out. Without this task, wrong
    #  numbers would be published silently.
    run_quality_checks = BashOperator(
        task_id="run_quality_checks",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && {DBT_BIN} test --profiles-dir {DBT_PROJECT_DIR} --target dev"
        ),
        execution_timeout=timedelta(minutes=15),
        doc_md="""
        Runs the dbt quality tests.

        BLOCKING tests (severity: error): key uniqueness and non-nullity,
        positive prices, strictly positive quantities, statuses belonging to the
        reference list, consistency between daily_sales and fct_orders.

        WARNING tests (severity: warn): referential integrity. Orphaned orders
        come from the upstream system and do not make the numbers wrong; we
        report them without blocking, with a threshold beyond which they become
        blocking again.
        """,
    )

    # -------------------------------------------------------------------------
    #  DEPENDENCIES
    # -------------------------------------------------------------------------
    #  With the TaskFlow API, passing one task's result to another is enough:
    #  Airflow derives the execution order from it and creates the matching
    #  XCom. No need to write `extract >> transform` by hand.
    #
    #  The "{{ ds }}" strings are Jinja templates rendered by Airflow just
    #  before execution: ds is the run's logical date, in YYYY-MM-DD format.
    extracted = extract_data(partition="{{ ds }}")
    transformed = transform_data(paths=extracted, partition="{{ ds }}")
    loaded = load_data(paths=transformed)

    #  For classic operators, the `>>` operator declares the dependency
    #  explicitly. It reads: "once this one has SUCCEEDED, start the next".
    #
    #      extract_data >> transform_data >> load_data >> run_dbt >> run_quality_checks
    #
    #  A dependency is not just an execution order: if load_data fails, run_dbt
    #  does not start at all and goes to `upstream_failed`. That is exactly what
    #  we want - rebuilding the analytical tables from data that was never
    #  loaded would produce wrong numbers.
    loaded >> run_dbt >> run_quality_checks


# Instantiate the DAG: without this call, Airflow would find nothing in this file.
ecommerce_daily_etl()
