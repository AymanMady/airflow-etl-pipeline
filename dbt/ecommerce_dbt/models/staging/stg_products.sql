-- =============================================================================
--  stg_products - the product preparation layer
-- =============================================================================

with source as (

    select * from {{ source('raw', 'products') }}

),

renamed as (

    select
        product_id,
        product_name,
        category,
        price,
        -- Price segmentation: a simple business rule, defined ONCE here
        -- rather than copied into every dashboard.
        case
            when price <  50  then 'budget'
            when price < 500  then 'standard'
            else                   'premium'
        end                      as price_segment,
        _loaded_at

    from source

)

select * from renamed
