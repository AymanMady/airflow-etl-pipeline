-- =============================================================================
--  dim_customers - the enriched CUSTOMER dimension
-- =============================================================================
--  One record per customer, with its descriptive attributes AND its
--  pre-computed activity metrics. Answering "who are my 10 best customers?"
--  becomes a plain ORDER BY, with no aggregation on the fly.
-- =============================================================================

with customers as (

    select * from {{ ref('stg_customers') }}

),

orders as (

    select * from {{ ref('fct_orders') }}

),

customer_orders as (

    select
        customer_id,
        count(*)                                                as orders_count,
        -- FILTER (WHERE ...) is the clean, standard-SQL way to aggregate
        -- only a subset. More readable than a SUM(CASE WHEN).
        count(*) filter (where is_revenue)                      as paid_orders_count,
        count(*) filter (where is_lost)                         as lost_orders_count,
        coalesce(sum(quantity) filter (where is_revenue), 0)    as total_items_bought,
        coalesce(sum(order_amount) filter (where is_revenue), 0) as lifetime_value,
        min(order_day)                                          as first_order_date,
        max(order_day)                                          as last_order_date

    from orders
    group by customer_id

)

select
    customers.customer_id,
    customers.first_name,
    customers.last_name,
    customers.full_name,
    customers.email,
    customers.has_valid_email,
    customers.country,
    customers.signup_date,

    -- COALESCE: a customer with no order at all must show 0, not NULL.
    -- Without it, an average over the column would skip those customers and
    -- overstate the mean value.
    coalesce(customer_orders.orders_count, 0)       as orders_count,
    coalesce(customer_orders.paid_orders_count, 0)  as paid_orders_count,
    coalesce(customer_orders.lost_orders_count, 0)  as lost_orders_count,
    coalesce(customer_orders.total_items_bought, 0) as total_items_bought,
    coalesce(customer_orders.lifetime_value, 0)     as lifetime_value,
    customer_orders.first_order_date,
    customer_orders.last_order_date,

    (customer_orders.customer_id is not null)       as is_active

from customers
left join customer_orders on customers.customer_id = customer_orders.customer_id
