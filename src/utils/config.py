"""Central configuration for the project.

Every value that changes between two environments (paths, database
credentials) is read here, in a single place. The rest of the code imports this
configuration instead of re-reading `os.environ` all over the place, so it is
clear exactly what the pipeline depends on to run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Project root, derived from the location of this file.
# src/utils/config.py -> parents[0]=utils, [1]=src, [2]=the project root.
# Works identically locally and inside the container (/opt/airflow).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"


@dataclass(frozen=True)
class PostgresConfig:
    """Connection parameters for the data warehouse.

    `frozen=True` makes the object immutable: once built, no piece of code can
    change the host or the password as a side effect.
    """

    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> PostgresConfig:
        """Build the configuration from the environment variables.

        Raises:
            KeyError: if a mandatory variable is missing. We fail early and
                loudly rather than connecting to an unexpected default
                database.
        """
        try:
            return cls(
                host=os.environ["POSTGRES_HOST"],
                port=int(os.environ.get("POSTGRES_PORT", 5432)),
                database=os.environ["POSTGRES_DB"],
                user=os.environ["POSTGRES_USER"],
                password=os.environ["POSTGRES_PASSWORD"],
            )
        except KeyError as exc:
            raise KeyError(
                f"Missing environment variable: {exc}. " "Check your .env file (see .env.example)."
            ) from exc

    @property
    def dsn(self) -> str:
        """psycopg2 connection string."""
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password}"
        )

    def __repr__(self) -> str:
        """Masks the password: these objects often end up in the logs."""
        return (
            f"PostgresConfig(host={self.host!r}, port={self.port}, "
            f"database={self.database!r}, user={self.user!r}, password='***')"
        )
