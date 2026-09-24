-- =============================================================================
--  Schema of the warehouse's `raw` layer
-- =============================================================================
--  Executed by src/load/load.py BEFORE every load. Everything is written as
--  CREATE ... IF NOT EXISTS, so the script can be replayed indefinitely without
--  error. That is already a form of idempotency, applied to the structure.
--
--  Why does the DDL live here rather than in docker-entrypoint-initdb.d?
--  Because init scripts only run on the container's very first start. A DDL
--  applied by the pipeline works on a fresh database as well as on an existing
--  one - including a production database nobody will ever recreate from
--  scratch.
-- =============================================================================

-- -----------------------------------------------------------------------------
--  raw.customers
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.customers (
    customer_id  INTEGER     PRIMARY KEY,
    first_name   TEXT        NOT NULL,
    last_name    TEXT,
    email        TEXT,                    -- NULL allowed: an invalid email was cleared
    country      TEXT,
    created_at   TIMESTAMP   NOT NULL,
    -- Technical column: when was this row loaded?
    -- Essential to audit a load ("did these rows come from the 01:00 run or
    -- from my manual test at 15:00?").
    _loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
--  raw.products
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.products (
    product_id   INTEGER        PRIMARY KEY,
    product_name TEXT           NOT NULL,
    category     TEXT,
    -- NUMERIC, not FLOAT: a binary float does not represent 19.99 exactly, and
    -- the rounding errors accumulate over a revenue sum.
    -- In finance you always use NUMERIC / DECIMAL.
    price        NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    _loaded_at   TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
--  raw.orders
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.orders (
    order_id     INTEGER     PRIMARY KEY,
    customer_id  INTEGER     NOT NULL,
    product_id   INTEGER     NOT NULL,
    quantity     INTEGER     NOT NULL CHECK (quantity > 0),
    order_date   TIMESTAMP   NOT NULL,
    status       TEXT        NOT NULL CHECK (
        status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled', 'returned')
    ),
    _loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
--  Why NO foreign key towards customers / products?
-- -----------------------------------------------------------------------------
--  This is a deliberate choice, not an oversight.
--
--  The `raw` layer has to stay FAITHFUL TO THE SOURCE. If the export holds an
--  order pointing at a non-existent customer, that is valuable information: it
--  reveals a problem in the upstream system. A foreign key would fail the whole
--  load over that single row, and the 4,712 valid orders would be lost too.
--
--  Those anomalies are caught further along, by the dbt `relationships` test
--  (PHASE 8): the pipeline loads everything, then REPORTS what is wrong.
--  Load first, measure next, alert last.
--
--  The CHECK constraints above are of a different nature: they deliberately
--  duplicate rules the transformation already applies. That is DEFENCE IN
--  DEPTH - if someone ever inserts data without going through the pipeline,
--  the database will still refuse a negative quantity.

-- -----------------------------------------------------------------------------
--  Index
-- -----------------------------------------------------------------------------
--  The daily aggregates filter and group on order_date: without an index,
--  every query re-reads the whole table.
CREATE INDEX IF NOT EXISTS idx_orders_order_date  ON raw.orders (order_date);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON raw.orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_product_id  ON raw.orders (product_id);
