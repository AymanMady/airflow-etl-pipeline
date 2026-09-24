-- =============================================================================
--  stg_customers - the customer preparation layer
-- =============================================================================
--  The role of staging: make the source CLEAN AND READABLE, with no business
--  logic at all. We rename, we type, we derive simple fields. Nothing more.
--
--  One staging model = one source. No join, no aggregate. That discipline
--  guarantees you can always trace a value back to its source without
--  guessing.
-- =============================================================================

with source as (

    select * from {{ source('raw', 'customers') }}

),

renamed as (

    select
        customer_id,
        first_name,
        last_name,
        -- Derived field: avoids re-joining first and last name in every query.
        trim(first_name || ' ' || coalesce(last_name, '')) as full_name,
        email,
        -- A customer with no valid email cannot be contacted: exposing it as
        -- an explicit boolean avoids reasoning about NULLs downstream.
        (email is not null)                                as has_valid_email,
        country,
        created_at,
        cast(created_at as date)                           as signup_date,
        _loaded_at

    from source

)

select * from renamed
