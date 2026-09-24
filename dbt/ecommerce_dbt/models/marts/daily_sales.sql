-- =============================================================================
--  daily_sales - the daily sales aggregate
-- =============================================================================
--  The table the business looks at first. One row per day.
--
--  Only the orders flagged `is_revenue` (paid / shipped / delivered) feed
--  revenue; cancellations and returns are counted separately, so they stay
--  visible.
-- =============================================================================

with orders as (

    select * from {{ ref('fct_orders') }}

),

daily as (

    select
        order_day                                                as sales_date,

        -- Volume
        count(*) filter (where is_revenue)                       as orders_count,
        count(distinct customer_id) filter (where is_revenue)    as customers_count,
        coalesce(sum(quantity) filter (where is_revenue), 0)     as total_quantity,

        -- Value
        coalesce(sum(order_amount) filter (where is_revenue), 0) as total_revenue,

        -- Losses, tracked separately: a rise in revenue that comes with a
        -- spike in cancellations is not good news.
        count(*) filter (where is_lost)                          as cancelled_orders_count,
        coalesce(sum(order_amount) filter (where is_lost), 0)    as lost_revenue

    from orders
    group by order_day

)

select
    sales_date,
    orders_count,
    customers_count,
    total_quantity,
    total_revenue,

    -- Average order value. The division is guarded by NULLIF: a day with no
    -- order would otherwise divide by zero, and the whole model would fail
    -- because of a single quiet day.
    round(total_revenue / nullif(orders_count, 0), 2) as average_order_value,

    cancelled_orders_count,
    lost_revenue

from daily
order by sales_date
