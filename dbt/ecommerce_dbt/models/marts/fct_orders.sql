-- =============================================================================
--  fct_orders - the order FACT table
-- =============================================================================
--  In a star schema you distinguish:
--
--    FACTS       what HAPPENED: events, dates and numeric measures. Many rows,
--                which accumulate. Here: an order.
--
--    DIMENSIONS  what DESCRIBES the facts: the attributes you want to filter
--                and group by. Few rows, changing slowly. Here: a customer, a
--                product.
--
--  The fact table is enriched with a few frequently used attributes (category,
--  country) to avoid two joins in every analytical query. That is deliberate
--  denormalisation: in analytics, read speed beats saving space.
-- =============================================================================

with orders as (

    select * from {{ ref('stg_orders') }}

),

products as (

    select * from {{ ref('stg_products') }}

),

customers as (

    select * from {{ ref('stg_customers') }}

),

joined as (

    select
        -- Keys
        orders.order_id,
        orders.customer_id,
        orders.product_id,

        -- Dates
        orders.order_date,
        orders.order_day,

        -- Status
        orders.status,
        orders.is_revenue,
        orders.is_lost,

        -- Measures
        orders.quantity,
        products.price                                   as unit_price,
        round(orders.quantity * products.price, 2)       as order_amount,

        -- Denormalised attributes, so analysis needs no extra join
        products.product_name,
        products.category,
        products.price_segment,
        customers.country                                as customer_country,

        -- Anomaly detection: an order whose product or customer cannot be
        -- found. The LEFT JOIN keeps it instead of making it disappear - a
        -- missing row goes unnoticed, a flagged row does not.
        (products.product_id  is null)                   as has_missing_product,
        (customers.customer_id is null)                  as has_missing_customer

    from orders
    -- LEFT JOIN, not INNER JOIN: an INNER would silently drop the orphaned
    -- orders, and revenue would fall without anyone knowing why.
    left join products  on orders.product_id  = products.product_id
    left join customers on orders.customer_id = customers.customer_id

)

select * from joined
