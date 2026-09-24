-- =============================================================================
--  No order may be dated in the future
-- =============================================================================
--  A future date almost always signals a time zone problem or a misread date
--  format (03/04 read as 4 March instead of 3 April). The symptom is subtle,
--  the consequence is not: a day's sales end up counted in the next month.
--
--  A one-day tolerance: the pipeline runs in UTC, and an order placed late in
--  the evening in a time zone ahead of it can legitimately look like
--  "tomorrow".
-- =============================================================================

select
    order_id,
    order_date
from {{ ref('fct_orders') }}
where order_date > current_date + interval '1 day'
