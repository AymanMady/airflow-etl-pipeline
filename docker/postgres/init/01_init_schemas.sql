-- =============================================================================
--  Initialisation of the e-commerce data warehouse
-- =============================================================================
--  This script is run AUTOMATICALLY by the official postgres image, once: on
--  the very first start, while the data volume is still empty. Every .sql file
--  placed in /docker-entrypoint-initdb.d is played in alphabetical order
--  (hence the "01_" prefix).
--
--  /!\ Editing this file afterwards has NO effect on an already initialised
--      database. To replay it:  make reset
-- =============================================================================

-- -----------------------------------------------------------------------------
--  Time zone: UTC everywhere
-- -----------------------------------------------------------------------------
--  Golden rule in data engineering: store and orchestrate in UTC, convert to
--  local time only for display. Airflow schedules in UTC; if the database
--  answered in Paris time, joins on dates would shift by one or two hours
--  depending on daylight saving. A very classic bug.
ALTER DATABASE ecommerce SET timezone TO 'UTC';

-- -----------------------------------------------------------------------------
--  The warehouse's 3 layers
-- -----------------------------------------------------------------------------
--  A professional warehouse separates data by LEVEL OF REFINEMENT. Each layer
--  has a clear owner and a clear contract:
--
--    raw       <- written by Python (PHASE 4). Data loaded as it came, typed
--                 but not business-shaped. A replayable source of truth.
--    staging   <- written by dbt (PHASE 7). Cleaning / renaming views.
--                 1 model = 1 source table. No business joins.
--    analytics <- written by dbt (PHASE 7). Final tables consumed by the
--                 analysts: dim_customers, dim_products, fct_orders,
--                 daily_sales.
--
--  The point: when a number is wrong, you walk the chain layer by layer to
--  locate the error, without ever re-extracting the source.

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA raw       IS 'Layer 1 - raw data loaded by the Python pipeline (ETL load)';
COMMENT ON SCHEMA staging   IS 'Layer 2 - dbt cleaning models, 1:1 with the sources';
COMMENT ON SCHEMA analytics IS 'Layer 3 - dbt analytical tables (dimensions, facts, aggregates)';

-- -----------------------------------------------------------------------------
--  Privileges
-- -----------------------------------------------------------------------------
--  The application user "ecommerce" writes to all 3 layers: here it is the same
--  account for Python and for dbt. In real production you would create two
--  distinct roles (etl_writer / dbt_writer) with separate privileges.
GRANT ALL PRIVILEGES ON SCHEMA raw, staging, analytics TO ecommerce;

-- -----------------------------------------------------------------------------
--  Verification trace
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    RAISE NOTICE '[INIT] ecommerce warehouse ready - schemas: raw, staging, analytics';
END
$$;
