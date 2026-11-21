# Slowly changing dimensions (type 2)

A type 2 dimension keeps one row per version of an entity instead of
overwriting it.

## Columns

| Column | Meaning |
|---|---|
| `customer_sk` | surrogate key, one per version |
| `customer_id` | natural key from the source |
| `valid_from` / `valid_to` | validity interval, `valid_to` open for the current row |
| `is_current` | convenience flag |

## Load logic

1. Compare incoming rows with current rows on a hash of tracked attributes.
2. For changed entities: close the current row (`valid_to = change time`).
3. Insert the new version with `valid_from = change time`.

In dbt this is what `snapshots` do with the `check` or `timestamp` strategy.

## Joining facts

Join on the natural key **and** `fact_date BETWEEN valid_from AND valid_to`, or
resolve the surrogate key at load time.
