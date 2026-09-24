#!/usr/bin/env bash
# =============================================================================
#  Demo: the pipeline is idempotent
# =============================================================================
#  Runs the pipeline twice in a row on the same source data and compares the
#  row counts in the database. A non-idempotent pipeline would double the
#  counters; this one has to leave them identical.
#
#  Usage:  make demo-idempotency
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source .env

PSQL="docker compose exec -T postgres-warehouse psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -tAc"

count_rows() {
    $PSQL "SELECT
             (SELECT count(*) FROM raw.customers) || ' / ' ||
             (SELECT count(*) FROM raw.products)  || ' / ' ||
             (SELECT count(*) FROM raw.orders)"
}

echo "==============================================================="
echo "  IDEMPOTENCY DEMONSTRATION"
echo "==============================================================="
echo
echo "  Initial state (customers / products / orders): $(count_rows)"
echo
echo "  --- RUN 1 -------------------------------------------------"
POSTGRES_HOST=localhost POSTGRES_PORT="${WAREHOUSE_HOST_PORT}" \
    .venv/bin/python scripts/run_pipeline.py 2>&1 | grep -E "inserted=|SUCCESS"
AFTER_RUN_1=$(count_rows)
echo
echo "  After run 1: ${AFTER_RUN_1}"
echo
echo "  --- RUN 2 (same source files, no change) ------------------"
POSTGRES_HOST=localhost POSTGRES_PORT="${WAREHOUSE_HOST_PORT}" \
    .venv/bin/python scripts/run_pipeline.py 2>&1 | grep -E "inserted=|SUCCESS"
AFTER_RUN_2=$(count_rows)
echo
echo "  After run 2: ${AFTER_RUN_2}"
echo
echo "==============================================================="
if [ "${AFTER_RUN_1}" = "${AFTER_RUN_2}" ]; then
    echo "  RESULT: IDEMPOTENT"
    echo "  The counters are identical. The second run updated the existing"
    echo "  rows (updated) instead of creating new ones."
else
    echo "  RESULT: NOT IDEMPOTENT - the counters changed!"
    exit 1
fi
echo "==============================================================="
