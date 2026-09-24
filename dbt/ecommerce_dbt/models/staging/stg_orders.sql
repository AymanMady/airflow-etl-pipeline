-- =============================================================================
--  stg_orders - the order preparation layer
-- =============================================================================

with source as (

    select * from {{ source('raw', 'orders') }}

),

renamed as (

    select
        order_id,
        customer_id,
        product_id,
        quantity,
        order_date,
        cast(order_date as date) as order_day,
        status,

        -- ---------------------------------------------------------------
        --  BUSINESS RULE: what counts as revenue?
        -- ---------------------------------------------------------------
        --  A cancelled or returned order generates no revenue. A pending
        --  order has not been paid yet.
        --  Only these count: paid, shipped, delivered.
        --
        --  This definition is THE most important decision in the project: it
        --  determines every figure presented to the business. It lives here,
        --  in a single versioned file, rather than scattered across the
        --  filters of fifteen dashboards.
        (status in ('paid', 'shipped', 'delivered')) as is_revenue,
        (status in ('cancelled', 'returned'))        as is_lost,
        _loaded_at

    from source

)

select * from renamed
