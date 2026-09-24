-- =============================================================================
--  Daily revenue must equal the sum of that day's orders
-- =============================================================================
--  This test compares an AGGREGATE against its SOURCE. It catches the most
--  dangerous class of analytics bugs: the one where everything looks fine but
--  the numbers are wrong - a join duplicating rows, a forgotten filter, a
--  GROUP BY on the wrong column.
--
--  A gap of less than a cent is tolerated: successive roundings over thousands
--  of rows do not always land exactly.
-- =============================================================================

with recalculated as (

    select
        order_day,
        sum(order_amount) as expected_revenue
    from {{ ref('fct_orders') }}
    where is_revenue
    group by order_day

),

comparison as (

    select
        daily.sales_date,
        daily.total_revenue,
        recalculated.expected_revenue,
        abs(daily.total_revenue - coalesce(recalculated.expected_revenue, 0)) as gap
    from {{ ref('daily_sales') }} as daily
    left join recalculated on daily.sales_date = recalculated.order_day

)

select * from comparison
where gap > 0.01
