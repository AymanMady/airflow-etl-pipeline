# Table grain

The **grain** is the sentence "one row per ...". Every table must have exactly
one, written in its documentation.

## Examples

| Table | Grain |
|---|---|
| `fct_order_items` | one row per order line |
| `fct_orders` | one row per order |
| `fct_daily_sales` | one row per store per day |
| `dim_customer` (SCD2) | one row per customer per version |

## Why it matters

- Joining a table to a finer-grained one multiplies rows and inflates sums.
- Mixing grains in one table (daily and monthly rows together) makes every
  aggregation wrong unless filtered.

## Enforcing it

Add a uniqueness test on the columns that define the grain, for example
`dbt_utils.unique_combination_of_columns` on `(store_id, date_day)`.
