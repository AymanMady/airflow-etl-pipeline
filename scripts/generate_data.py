#!/usr/bin/env python3
"""Generate the demo e-commerce source CSVs.

This script simulates a daily export from an operational system. The data is
deliberately IMPERFECT: duplicates, missing values, malformed emails, negative
prices, zero quantities, unknown statuses, inconsistent date formats, orphaned
references.

Why dirty the data on purpose? Because a pipeline tested only on clean data
proves nothing. In real life the source data is always dirty, and making it
usable - or refusing to load it - is precisely the pipeline's job.

The generator is DETERMINISTIC (fixed seed): two runs produce identical files.
That is essential for the tests to be stable.

Usage:
    python scripts/generate_data.py
    python scripts/generate_data.py --orders 20000 --seed 7
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.config import RAW_DATA_DIR  # noqa: E402
from src.utils.logging_setup import get_logger  # noqa: E402

logger = get_logger("GENERATE")

# --- Generation vocabulary ----------------------------------------------------
FIRST_NAMES = [
    "Amadou",
    "Fatima",
    "Jean",
    "Marie",
    "Youssef",
    "Aicha",
    "Pierre",
    "Sophie",
    "Omar",
    "Khadija",
    "Luc",
    "Elena",
    "Ibrahim",
    "Nora",
    "Thomas",
    "Camille",
    "Moussa",
    "Leila",
    "Antoine",
    "Ines",
    "Karim",
    "Clara",
    "Hugo",
    "Awa",
]
LAST_NAMES = [
    "Diallo",
    "Martin",
    "Ba",
    "Dubois",
    "Benali",
    "Moreau",
    "Sow",
    "Laurent",
    "Traore",
    "Simon",
    "Ndiaye",
    "Garcia",
    "Cisse",
    "Rossi",
    "Fall",
    "Muller",
]
COUNTRIES = [
    "France",
    "Belgium",
    "Switzerland",
    "Canada",
    "Morocco",
    "Senegal",
    "Mauritania",
    "Germany",
    "Spain",
    "Italy",
]
CATEGORIES = {
    "Electronics": ["Laptop", "Smartphone", "Headphones", "Tablet", "Monitor", "Keyboard"],
    "Clothing": ["T-Shirt", "Jeans", "Jacket", "Sneakers", "Dress", "Scarf"],
    "Home": ["Lamp", "Chair", "Rug", "Mug Set", "Blanket", "Cookware"],
    "Books": ["Novel", "Cookbook", "Biography", "Atlas", "Poetry", "Textbook"],
    "Sports": ["Yoga Mat", "Dumbbells", "Running Shoes", "Backpack", "Bicycle Helmet"],
    "Beauty": ["Shampoo", "Perfume", "Face Cream", "Lipstick", "Razor"],
}
BRANDS = ["Nova", "Orion", "Lumen", "Vertex", "Aura", "Zenith", "Terra", "Pulse"]
STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled", "returned"]
STATUS_WEIGHTS = [5, 20, 15, 50, 7, 3]

# --- Injected anomaly rates (share of rows affected) --------------------------
RATE_DUPLICATE = 0.02  # rows duplicated verbatim
RATE_NULL_VALUE = 0.03  # field left empty
RATE_DIRTY_EMAIL = 0.08  # upper case, spaces, or a missing @
RATE_DIRTY_TEXT = 0.10  # stray whitespace, inconsistent casing
RATE_BAD_PRICE = 0.02  # negative or zero price
RATE_BAD_QUANTITY = 0.02  # zero or negative quantity
RATE_BAD_STATUS = 0.02  # status outside the reference list
RATE_ALT_DATE_FORMAT = 0.12  # date in another format
RATE_ORPHAN_REF = 0.01  # order pointing at a non-existent customer


def _messy_text(value: str, rng: random.Random) -> str:
    """Mangle a text field the way human data entry would."""
    roll = rng.random()
    if roll < 0.4:
        return f"  {value} "  # stray whitespace
    if roll < 0.7:
        return value.upper()  # all upper case
    return value.lower()  # all lower case


def _messy_email(email: str, rng: random.Random) -> str:
    """Mangle an email address."""
    roll = rng.random()
    if roll < 0.35:
        return email.upper()
    if roll < 0.60:
        return f" {email} "
    if roll < 0.85:
        return email.replace("@", "")  # invalid email: no @
    return email.replace(".com", "")  # truncated domain


def _format_date(value: datetime, rng: random.Random) -> str:
    """Format a date, sometimes in an alternative format."""
    if rng.random() < RATE_ALT_DATE_FORMAT:
        return (
            value.strftime("%d/%m/%Y")
            if rng.random() < 0.5
            else value.strftime("%Y-%m-%d %H:%M:%S")
        )
    return value.strftime("%Y-%m-%d")


def generate_customers(count: int, rng: random.Random, today: datetime) -> list[dict]:
    """Generate the customers table."""
    rows = []
    for i in range(1, count + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        email = f"{first.lower()}.{last.lower()}{i}@example.com"
        created = today - timedelta(days=rng.randint(30, 900))

        row = {
            "customer_id": i,
            "first_name": _messy_text(first, rng) if rng.random() < RATE_DIRTY_TEXT else first,
            "last_name": last,
            "email": _messy_email(email, rng) if rng.random() < RATE_DIRTY_EMAIL else email,
            "country": rng.choice(COUNTRIES),
            "created_at": _format_date(created, rng),
        }
        if rng.random() < RATE_DIRTY_TEXT:
            row["country"] = _messy_text(row["country"], rng)
        if rng.random() < RATE_NULL_VALUE:
            row[rng.choice(["email", "country", "last_name"])] = ""
        rows.append(row)
    return rows


def generate_products(count: int, rng: random.Random) -> list[dict]:
    """Generate the product catalogue."""
    rows = []
    for i in range(1, count + 1):
        category = rng.choice(list(CATEGORIES))
        name = f"{rng.choice(BRANDS)} {rng.choice(CATEGORIES[category])}"
        price = round(rng.uniform(5, 1500), 2)

        row = {
            "product_id": i,
            "product_name": name,
            "category": _messy_text(category, rng) if rng.random() < RATE_DIRTY_TEXT else category,
            "price": price,
        }
        if rng.random() < RATE_BAD_PRICE:
            row["price"] = round(-price, 2) if rng.random() < 0.5 else 0
        if rng.random() < RATE_NULL_VALUE:
            row["price"] = ""
        rows.append(row)
    return rows


def generate_orders(
    count: int,
    customer_count: int,
    product_count: int,
    rng: random.Random,
    today: datetime,
    days: int,
) -> list[dict]:
    """Generate the orders, spread over the last `days` days."""
    rows = []
    for i in range(1, count + 1):
        order_date = today - timedelta(
            days=rng.randint(0, days - 1),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        customer_id = rng.randint(1, customer_count)
        if rng.random() < RATE_ORPHAN_REF:
            customer_id = customer_count + rng.randint(1, 50)  # non-existent customer

        row = {
            "order_id": i,
            "customer_id": customer_id,
            "product_id": rng.randint(1, product_count),
            "quantity": rng.choices([1, 2, 3, 4, 5], weights=[50, 25, 12, 8, 5])[0],
            "order_date": _format_date(order_date, rng),
            "status": rng.choices(STATUSES, weights=STATUS_WEIGHTS)[0],
        }
        if rng.random() < RATE_BAD_QUANTITY:
            row["quantity"] = rng.choice([0, -1, -3])
        if rng.random() < RATE_BAD_STATUS:
            row["status"] = rng.choice(["PAID", "Shipped", "unknown", "in_progress", ""])
        if rng.random() < RATE_NULL_VALUE:
            row[rng.choice(["quantity", "status"])] = ""
        rows.append(row)
    return rows


def inject_duplicates(rows: list[dict], rng: random.Random) -> list[dict]:
    """Duplicate a fraction of the rows verbatim, then shuffle.

    A very common real case: an export rerun after a network incident
    concatenates the same records twice.
    """
    n = int(len(rows) * RATE_DUPLICATE)
    duplicates = [dict(row) for row in rng.sample(rows, n)] if n else []
    combined = rows + duplicates
    rng.shuffle(combined)
    return combined


def write_csv(rows: list[dict], path: Path, columns: list[str]) -> None:
    """Write the rows to a UTF-8 CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %-14s %6d rows -> %s", path.name, len(rows), path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customers", type=int, default=500)
    parser.add_argument("--products", type=int, default=60)
    parser.add_argument("--orders", type=int, default=5000)
    parser.add_argument("--days", type=int, default=90, help="depth of history")
    parser.add_argument("--seed", type=int, default=42, help="seed (reproducibility)")
    parser.add_argument("--output-dir", type=Path, default=RAW_DATA_DIR)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    logger.info("=" * 62)
    logger.info("[GENERATE] Generating the source CSVs (seed=%d)", args.seed)
    logger.info("=" * 62)

    customers = inject_duplicates(generate_customers(args.customers, rng, today), rng)
    products = generate_products(args.products, rng)
    orders = inject_duplicates(
        generate_orders(args.orders, args.customers, args.products, rng, today, args.days),
        rng,
    )

    write_csv(
        customers,
        args.output_dir / "customers.csv",
        ["customer_id", "first_name", "last_name", "email", "country", "created_at"],
    )
    write_csv(
        products,
        args.output_dir / "products.csv",
        ["product_id", "product_name", "category", "price"],
    )
    write_csv(
        orders,
        args.output_dir / "orders.csv",
        ["order_id", "customer_id", "product_id", "quantity", "order_date", "status"],
    )

    logger.info("-" * 62)
    logger.info("[GENERATE] Deliberately injected anomalies:")
    logger.info(
        "  duplicates ~%.0f%% | null values ~%.0f%% | dirty emails ~%.0f%%",
        RATE_DUPLICATE * 100,
        RATE_NULL_VALUE * 100,
        RATE_DIRTY_EMAIL * 100,
    )
    logger.info(
        "  invalid prices ~%.0f%% | invalid quantities ~%.0f%% | unknown statuses ~%.0f%%",
        RATE_BAD_PRICE * 100,
        RATE_BAD_QUANTITY * 100,
        RATE_BAD_STATUS * 100,
    )
    logger.info(
        "  dates in an alternative format ~%.0f%% | orphaned references ~%.0f%%",
        RATE_ALT_DATE_FORMAT * 100,
        RATE_ORPHAN_REF * 100,
    )
    logger.info("[GENERATE] Done. It is up to the pipeline to clean all that up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
