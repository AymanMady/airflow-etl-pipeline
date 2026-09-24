"""Tests of the LOAD step.

These are INTEGRATION tests: they need a real PostgreSQL. We do not fake the
database with a mock, because what we want to check here is precisely
PostgreSQL's behaviour - the UPSERT, the CHECK constraints, the transactional
rollback. A mock would only confirm that the code calls the functions we think
it calls.

Run only these tests:   make test-integration
Exclude them:           pytest -m "not integration"
"""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
import psycopg2
import pytest

from src.load.load import ensure_schema, get_connection, load_dataset
from src.utils.config import PostgresConfig
from src.utils.datasets import CUSTOMERS, ORDERS, PRODUCTS
from src.utils.exceptions import LoadError

pytestmark = pytest.mark.integration

#: Identifier range reserved for the tests. It cannot collide with the demo
#: data (which stops at 5,100), and it makes cleaning up after each test safe.
TEST_ID_BASE = 900_000


@pytest.fixture
def conn(pg_config: PostgresConfig) -> Iterator:
    """Connection to the warehouse, cleaning up the test rows at the end."""
    try:
        connection = get_connection(pg_config)
    except LoadError as error:
        pytest.skip(f"PostgreSQL unavailable ({error}). Run: make up")

    ensure_schema(connection)
    yield connection

    # Systematic cleanup, even when the test failed: a test must never leave
    # a trace in the database.
    with connection.cursor() as cursor:
        for table in ("orders", "products", "customers"):
            cursor.execute(f"DELETE FROM raw.{table} WHERE {table[:-1]}_id >= %s", (TEST_ID_BASE,))
    connection.commit()
    connection.close()


def _customers(count: int, country: str = "Testland") -> pd.DataFrame:
    """Build a set of test customers."""
    return pd.DataFrame(
        {
            "customer_id": pd.array(range(TEST_ID_BASE, TEST_ID_BASE + count), dtype="Int64"),
            "first_name": [f"Test{i}" for i in range(count)],
            "last_name": ["Client"] * count,
            "email": [f"test{i}@example.com" for i in range(count)],
            "country": [country] * count,
            "created_at": pd.to_datetime(["2026-01-01"] * count),
        }
    )


def _count(conn, table: str) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            f"SELECT count(*) FROM raw.{table} WHERE {table[:-1]}_id >= %s", (TEST_ID_BASE,)
        )
        return cursor.fetchone()[0]


class TestInsertion:
    """Does the load insert correctly?"""

    def test_inserts_all_rows(self, conn):
        stats = load_dataset(conn, CUSTOMERS, _customers(10))

        assert stats["processed"] == 10
        assert stats["inserted"] == 10
        assert _count(conn, "customers") == 10

    def test_values_are_stored_faithfully(self, conn):
        load_dataset(conn, CUSTOMERS, _customers(1, country="Senegal"))

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT first_name, email, country FROM raw.customers WHERE customer_id = %s",
                (TEST_ID_BASE,),
            )
            first_name, email, country = cursor.fetchone()

        assert (first_name, email, country) == ("Test0", "test0@example.com", "Senegal")

    def test_null_values_become_sql_null(self, conn):
        """pandas' missing values must become NULL, not "NaN"."""
        frame = _customers(1)
        frame.loc[0, "email"] = pd.NA

        load_dataset(conn, CUSTOMERS, frame)

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT email IS NULL FROM raw.customers WHERE customer_id = %s", (TEST_ID_BASE,)
            )
            assert cursor.fetchone()[0] is True


class TestIdempotency:
    """THE most important test in the project."""

    def test_running_twice_does_not_duplicate(self, conn):
        """Run 1: 100 rows. Run 2: still 100 rows, not 200."""
        frame = _customers(100)

        first = load_dataset(conn, CUSTOMERS, frame)
        second = load_dataset(conn, CUSTOMERS, frame)

        assert first["inserted"] == 100
        assert second["inserted"] == 0  # no new row
        assert second["updated"] == 100  # everything was updated
        assert _count(conn, "customers") == 100

    def test_running_ten_times_is_stable(self, conn):
        """Idempotency does not degrade with the number of reruns."""
        frame = _customers(20)

        for _ in range(10):
            load_dataset(conn, CUSTOMERS, frame)

        assert _count(conn, "customers") == 20

    def test_upsert_updates_changed_values(self, conn):
        """A value changed at the source must be reflected."""
        load_dataset(conn, CUSTOMERS, _customers(1, country="France"))
        load_dataset(conn, CUSTOMERS, _customers(1, country="Canada"))

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT country FROM raw.customers WHERE customer_id = %s", (TEST_ID_BASE,)
            )
            assert cursor.fetchone()[0] == "Canada"

        assert _count(conn, "customers") == 1

    def test_loaded_at_is_refreshed_on_update(self, conn):
        """The technical column _loaded_at must record the last load."""
        frame = _customers(1)
        load_dataset(conn, CUSTOMERS, frame)

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT _loaded_at FROM raw.customers WHERE customer_id = %s", (TEST_ID_BASE,)
            )
            first_load = cursor.fetchone()[0]

        load_dataset(conn, CUSTOMERS, frame)

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT _loaded_at FROM raw.customers WHERE customer_id = %s", (TEST_ID_BASE,)
            )
            second_load = cursor.fetchone()[0]

        assert second_load > first_load


class TestDatabaseConstraints:
    """Does the database refuse invalid data?

    These constraints deliberately duplicate rules the transformation already
    applies. That is defence in depth: they protect the database against an
    insert that never went through the pipeline.
    """

    def test_rejects_negative_quantity(self, conn):
        frame = pd.DataFrame(
            {
                "order_id": pd.array([TEST_ID_BASE], dtype="Int64"),
                "customer_id": pd.array([TEST_ID_BASE], dtype="Int64"),
                "product_id": pd.array([TEST_ID_BASE], dtype="Int64"),
                "quantity": pd.array([-5], dtype="Int64"),
                "order_date": pd.to_datetime(["2026-01-01"]),
                "status": ["paid"],
            }
        )

        with pytest.raises(LoadError):
            load_dataset(conn, ORDERS, frame)

    def test_rejects_unknown_status(self, conn):
        frame = pd.DataFrame(
            {
                "order_id": pd.array([TEST_ID_BASE], dtype="Int64"),
                "customer_id": pd.array([TEST_ID_BASE], dtype="Int64"),
                "product_id": pd.array([TEST_ID_BASE], dtype="Int64"),
                "quantity": pd.array([1], dtype="Int64"),
                "order_date": pd.to_datetime(["2026-01-01"]),
                "status": ["made_up_status"],
            }
        )

        with pytest.raises(LoadError):
            load_dataset(conn, ORDERS, frame)

    def test_rejects_negative_price(self, conn):
        frame = pd.DataFrame(
            {
                "product_id": pd.array([TEST_ID_BASE], dtype="Int64"),
                "product_name": ["Test product"],
                "category": ["Test"],
                "price": [-10.0],
            }
        )

        with pytest.raises(LoadError):
            load_dataset(conn, PRODUCTS, frame)


class TestTransactionSafety:
    """Does an error leave the table in a coherent state?"""

    def test_failed_load_leaves_table_untouched(self, conn):
        """All or nothing: a single bad row cancels the whole batch."""
        load_dataset(conn, CUSTOMERS, _customers(5))
        before = _count(conn, "customers")

        invalid = _customers(5)
        invalid.loc[2, "first_name"] = pd.NA  # violates the NOT NULL constraint

        with pytest.raises(LoadError):
            load_dataset(conn, CUSTOMERS, invalid)

        assert _count(conn, "customers") == before

    def test_connection_is_usable_after_a_failure(self, conn):
        """The rollback must leave the connection reusable."""
        invalid = _customers(1)
        invalid.loc[0, "first_name"] = pd.NA

        with pytest.raises(LoadError):
            load_dataset(conn, CUSTOMERS, invalid)

        # Without the rollback, PostgreSQL would refuse every following query
        # with "current transaction is aborted".
        stats = load_dataset(conn, CUSTOMERS, _customers(3))
        assert stats["processed"] == 3


class TestConnectionErrors:
    """Behaviour when the database is unreachable."""

    def test_raises_load_error_on_bad_host(self):
        config = PostgresConfig(
            host="nonexistent-host", port=5432, database="x", user="x", password="x"
        )

        with pytest.raises(LoadError) as error:
            get_connection(config)

        assert "make ps" in str(error.value)

    def test_password_is_masked_in_error_messages(self):
        """A password must never appear in an error log."""
        config = PostgresConfig(
            host="nonexistent-host",
            port=5432,
            database="x",
            user="x",
            password="super_secret_password",
        )

        with pytest.raises(LoadError) as error:
            get_connection(config)

        assert "super_secret_password" not in str(error.value)
        assert "***" in str(error.value)


def test_psycopg2_is_available():
    """Guard rail: check that the driver really is installed."""
    assert psycopg2.__version__
