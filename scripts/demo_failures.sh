#!/usr/bin/env bash
# =============================================================================
#  Demo: how the pipeline fails
# =============================================================================
#  Simulates three real failures and shows the error message produced.
#  A good error message answers three questions:
#      WHAT   which step failed
#      WHY    the precise cause
#      HOW    what to do to fix it
#
#  Each failure is restored immediately after the demonstration.
#
#  Usage:  make demo-failures
# =============================================================================
set -uo pipefail

cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source .env

run_pipeline() {
    POSTGRES_HOST=localhost POSTGRES_PORT="${WAREHOUSE_HOST_PORT}" \
        .venv/bin/python scripts/run_pipeline.py 2>&1 | grep -A5 "FAILED\|SUCCESS" | head -8
}

echo "==============================================================="
echo "  FAILURE 1 - missing source file"
echo "  This error is NOT retryable: rerunning will not make the"
echo "  file appear."
echo "==============================================================="
mv data/raw/customers.csv /tmp/customers.csv.demo
run_pipeline
mv /tmp/customers.csv.demo data/raw/customers.csv

echo
echo "==============================================================="
echo "  FAILURE 2 - column missing from the source"
echo "  Not retryable: the file structure will not change."
echo "==============================================================="
cp data/raw/products.csv /tmp/products.csv.demo
python3 - <<'PY'
import csv
cols = ["product_id", "product_name", "category"]          # "price" removed
rows = list(csv.DictReader(open("data/raw/products.csv")))
with open("data/raw/products.csv", "w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=cols)
    writer.writeheader()
    writer.writerows([{key: row[key] for key in cols} for row in rows])
PY
run_pipeline
cp /tmp/products.csv.demo data/raw/products.csv

echo
echo "==============================================================="
echo "  FAILURE 3 - database unavailable"
echo "  This one IS retryable: a database that restarts becomes"
echo "  reachable again. This is exactly the case Airflow retries"
echo "  are made to absorb."
echo "==============================================================="
docker compose stop postgres-warehouse >/dev/null 2>&1
run_pipeline
docker compose start postgres-warehouse >/dev/null 2>&1
echo "  ... restarting the database ..."
until docker compose exec -T postgres-warehouse pg_isready -q -U "${POSTGRES_USER}" 2>/dev/null; do sleep 2; done

echo
echo "==============================================================="
echo "  BACK TO NORMAL"
echo "==============================================================="
run_pipeline
echo
echo "  Note: the password shows up masked (***) in the message of"
echo "  failure 3. A secret must never leak into a log."
