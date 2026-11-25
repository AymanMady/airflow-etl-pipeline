# `scripts/generate_data.py`

> Generate the demo e-commerce source CSVs.

Reference for the public API of `scripts/generate_data.py` (322 lines),
extracted from the source code: signatures and docstrings.

## Imports

- Project: `src.utils.config`, `src.utils.logging_setup`
- Standard library: `argparse`, `csv`, `datetime`, `pathlib`, `random`, `sys`

## Constants

- `FIRST_NAMES` (list of 24 items)
- `LAST_NAMES` (list of 16 items)
- `COUNTRIES` (list of 10 items)
- `CATEGORIES` (dict with 6 keys)
- `BRANDS` (list of 8 items)
- `STATUSES` (list of 6 items)
- `STATUS_WEIGHTS = [5, 20, 15, 50, 7, 3]`
- `RATE_DUPLICATE = 0.02`
- `RATE_NULL_VALUE = 0.03`
- `RATE_DIRTY_EMAIL = 0.08`
- `RATE_DIRTY_TEXT = 0.1`
- `RATE_BAD_PRICE = 0.02`
- `RATE_BAD_QUANTITY = 0.02`
- `RATE_BAD_STATUS = 0.02`
- `RATE_ALT_DATE_FORMAT = 0.12`
- `RATE_ORPHAN_REF = 0.01`

## Functions

### `generate_customers`

```python
generate_customers(count: int, rng: random.Random, today: datetime) -> list[dict]
```

Generate the customers table.

### `generate_products`

```python
generate_products(count: int, rng: random.Random) -> list[dict]
```

Generate the product catalogue.

### `generate_orders`

```python
generate_orders(count: int, customer_count: int, product_count: int, rng: random.Random, today: datetime, days: int) -> list[dict]
```

Generate the orders, spread over the last `days` days.

### `inject_duplicates`

```python
inject_duplicates(rows: list[dict], rng: random.Random) -> list[dict]
```

Duplicate a fraction of the rows verbatim, then shuffle.

### `write_csv`

```python
write_csv(rows: list[dict], path: Path, columns: list[str]) -> None
```

Write the rows to a UTF-8 CSV.

### `main`

```python
main() -> int
```

## Usage

This module is also a script:

```bash
python scripts/generate_data.py
```
