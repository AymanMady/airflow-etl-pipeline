# `dbt/ecommerce_dbt/tests/assert_no_future_orders.sql`

> No order may be dated in the future  
> A future date almost always signals a time zone problem or a misread date  
> format (03/04 read as 4 March instead of 3 April). The symptom is subtle,  
> the consequence is not: a day's sales end up counted in the next month.

- **Kind**: dbt model
- **Size**: 17 lines, 1 statement(s)

## Upstream dependencies

- model `fct_orders` (via `ref`)
