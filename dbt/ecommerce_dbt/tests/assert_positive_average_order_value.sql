-- =============================================================================
--  The average order value must be strictly positive and plausible
-- =============================================================================
--  A guard rail against two classic mistakes: a botched division producing 0,
--  and a unit error (cents treated as euros) producing an absurd average
--  basket.
--
--  The upper bound is a BUSINESS rule, not a mathematical truth: on this shop,
--  an average order value above 100,000 EUR signals a bug, not a good day.
-- =============================================================================

select
    sales_date,
    average_order_value
from {{ ref('daily_sales') }}
where average_order_value <= 0
   or average_order_value > 100000
