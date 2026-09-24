"""Fixtures shared by the tests.

A pytest fixture is a piece of data or an object prepared before a test and
cleaned up afterwards. It avoids copying the same scaffolding into every test
and guarantees each one starts from a known state.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from dotenv import load_dotenv

from src.utils.config import PROJECT_ROOT, PostgresConfig


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    """Temporary folder standing in for data/raw/.

    `tmp_path` is provided by pytest: a fresh folder per test, deleted
    automatically afterwards. No test ever touches the real data.
    """
    directory = tmp_path / "raw"
    directory.mkdir()
    return directory


@pytest.fixture
def valid_customers_csv(raw_dir: Path) -> Path:
    """A minimal customers.csv that still satisfies the contract."""
    path = raw_dir / "customers.csv"
    path.write_text(
        "customer_id,first_name,last_name,email,country,created_at\n"
        "1,Amadou,Diallo,amadou.diallo@example.com,Senegal,2025-01-15\n"
        "2,Marie,Dubois,marie.dubois@example.com,France,2025-02-20\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def dirty_customers() -> pd.DataFrame:
    """Raw customers holding one of every anomaly category.

    Everything is text: exactly what extraction produces.
    """
    return pd.DataFrame(
        {
            "customer_id": ["1", "2", "2", "3", "", "5"],
            "first_name": ["  Amadou ", "MARIE", "MARIE", "jean", "Paul", "Awa"],
            "last_name": ["Diallo", "Dubois", "Dubois", "Martin", "Durand", ""],
            "email": [
                "AMADOU.DIALLO@EXAMPLE.COM",  # upper case -> to normalise
                " marie@example.com ",  # spaces -> to strip
                " marie@example.com ",  # duplicate
                "jean-without-at-sign",  # invalid -> must become NULL
                "paul@example.com",  # missing id -> row rejected
                "awa@example.com",
            ],
            "country": ["senegal", "FRANCE", "FRANCE", " France ", "France", "Mali"],
            "created_at": [
                "2025-01-15",  # ISO format
                "20/02/2025",  # day/month/year format
                "20/02/2025",
                "2025-03-10 14:30:00",  # ISO with a time
                "2025-04-01",
                "not-a-date",  # not parsable -> row rejected
            ],
        }
    )


@pytest.fixture
def dirty_products() -> pd.DataFrame:
    """Raw products with invalid prices."""
    return pd.DataFrame(
        {
            "product_id": ["1", "2", "3", "4"],
            "product_name": ["Nova Laptop", "Orion Mug", "Lumen Lamp", "Aura Book"],
            "category": ["electronics", "HOME", " Home ", "Books"],
            "price": ["999.99", "-15.00", "", "12.50"],
        }
    )


@pytest.fixture
def dirty_orders() -> pd.DataFrame:
    """Raw orders with invalid quantities and statuses."""
    return pd.DataFrame(
        {
            "order_id": ["1", "2", "3", "4", "5", "6"],
            "customer_id": ["1", "1", "2", "3", "1", "1"],
            "product_id": ["1", "2", "1", "4", "1", "1"],
            "quantity": ["2", "0", "-1", "3", "", "1"],
            "order_date": [
                "2026-09-01",
                "2026-09-02",
                "2026-09-03",
                "2026-09-04",
                "2026-09-05",
                "2026-09-06",
            ],
            "status": ["delivered", "paid", "paid", "PAID", "paid", "unknown_status"],
        }
    )


@pytest.fixture(scope="session")
def pg_config() -> PostgresConfig:
    """PostgreSQL configuration for the integration tests.

    No password is hardcoded here: a secret has no place in a versioned file,
    not even for a development environment. The values are read, in order of
    precedence:

        1. the environment variables already defined (the container case);
        2. the .env file at the project root (the local machine case).

    From the host, the warehouse answers on localhost:5435; from a container,
    on postgres-warehouse:5432.
    """
    # load_dotenv never replaces a variable already present in the
    # environment, so the container keeps its own configuration.
    load_dotenv(PROJECT_ROOT / ".env")

    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        pytest.skip("POSTGRES_PASSWORD missing - create .env with `make init`")

    return PostgresConfig(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        # From the host, the published port is what matters, not the internal one.
        port=int(os.getenv("POSTGRES_PORT") or os.getenv("WAREHOUSE_HOST_PORT", "5435")),
        database=os.getenv("POSTGRES_DB", "ecommerce"),
        user=os.getenv("POSTGRES_USER", "ecommerce"),
        password=password,
    )
