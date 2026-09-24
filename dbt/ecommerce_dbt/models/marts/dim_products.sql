-- =============================================================================
--  dim_products - the enriched PRODUCT dimension
-- =============================================================================

with products as (

    select * from {{ ref('stg_products') }}

),

orders as (

    select * from {{ ref('fct_orders') }}

),

product_orders as (

    select
        product_id,
        count(*)                                                 as orders_count,
        coalesce(sum(quantity) filter (where is_revenue), 0)     as units_sold,
        coalesce(sum(order_amount) filter (where is_revenue), 0) as total_revenue,
        count(*) filter (where is_lost)                          as lost_orders_count

    from orders
    group by product_id

)

select
    products.product_id,
    products.product_name,
    products.category,
    products.price,
    products.price_segment,

    coalesce(product_orders.orders_count, 0)      as orders_count,
    coalesce(product_orders.units_sold, 0)        as units_sold,
    coalesce(product_orders.total_revenue, 0)     as total_revenue,
    coalesce(product_orders.lost_orders_count, 0) as lost_orders_count,

    (coalesce(product_orders.units_sold, 0) = 0)  as is_never_sold

from products
left join product_orders on products.product_id = product_orders.product_id
