"""Registry of the pipeline's datasets.

Single source of truth: the file name, the primary key and the expected columns
of each dataset are declared HERE, once. Extraction, transformation, loading
and the tests all refer to it.

Without this registry the column list would be copied into four different
files; the day a column changes, one of them would be forgotten.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetSpec:
    """The contract of a source dataset.

    Attributes:
        name: logical identifier, reused as the table name.
        filename: name of the CSV file in data/raw/.
        primary_key: the column that identifies a row uniquely. It is what
            makes the load idempotent (PHASE 4).
        required_columns: columns that MUST be present. If one is missing,
            extraction fails immediately.
    """

    name: str
    filename: str
    primary_key: str
    required_columns: tuple[str, ...]


CUSTOMERS = DatasetSpec(
    name="customers",
    filename="customers.csv",
    primary_key="customer_id",
    required_columns=(
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "country",
        "created_at",
    ),
)

PRODUCTS = DatasetSpec(
    name="products",
    filename="products.csv",
    primary_key="product_id",
    required_columns=("product_id", "product_name", "category", "price"),
)

ORDERS = DatasetSpec(
    name="orders",
    filename="orders.csv",
    primary_key="order_id",
    required_columns=(
        "order_id",
        "customer_id",
        "product_id",
        "quantity",
        "order_date",
        "status",
    ),
)

#: Every dataset, in load order.
#: Orders come last: they reference customers and products.
DATASETS: dict[str, DatasetSpec] = {
    CUSTOMERS.name: CUSTOMERS,
    PRODUCTS.name: PRODUCTS,
    ORDERS.name: ORDERS,
}

#: Allowed order statuses. Any other value is an anomaly.
VALID_ORDER_STATUSES: frozenset[str] = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "returned"}
)
