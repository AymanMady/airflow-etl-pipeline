# =============================================================================
#  ecommerce-etl - Makefile
# =============================================================================
#  The project's single entry point. Rather than memorising long Docker
#  commands, it exposes short, documented verbs.
#  Just type `make` to see everything available.
# =============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash
COMPOSE := docker compose
PYTHON := .venv/bin/python

# Load .env so the targets can use $(POSTGRES_USER) and friends.
ifneq (,$(wildcard .env))
	include .env
	export
endif

# dbt lives in its own venv, inside the Airflow container.
DBT := docker compose exec -T airflow-scheduler bash -c "cd /opt/airflow/dbt/ecommerce_dbt && /opt/dbt_venv/bin/dbt

# .PHONY declares the targets that do not produce a file of the same name.
# Without it, a folder called "logs" would stop `make logs` from running.
.PHONY: help init venv seed up down restart ps logs psql tools reset clean \
        run-local test test-unit test-integration lint \
        dbt-run dbt-test dbt-docs \
        airflow airflow-logs trigger unpause backfill demo-idempotency demo-failures

# -----------------------------------------------------------------------------
#  Help
# -----------------------------------------------------------------------------
help: ## Show this help
	@echo ""
	@echo "  ecommerce-etl - e-commerce ETL pipeline orchestrated by Airflow"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(firstword $(MAKEFILE_LIST)) \
	| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# -----------------------------------------------------------------------------
#  Installation
# -----------------------------------------------------------------------------
init: ## Create the .env file from .env.example
	@if [ -f .env ]; then \
	echo "  .env already exists - nothing to do (delete it to start over)"; \
	else \
	cp .env.example .env; \
	sed -i "s/^AIRFLOW_UID=.*/AIRFLOW_UID=$$(id -u)/" .env; \
	sed -i "s|^AIRFLOW_FERNET_KEY=.*|AIRFLOW_FERNET_KEY=$$(python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')|" .env; \
	sed -i "s|^AIRFLOW_JWT_SECRET=.*|AIRFLOW_JWT_SECRET=$$(python3 -c 'import secrets; print(secrets.token_hex(32))')|" .env; \
	echo "  .env created with generated keys - remember to change the passwords"; \
	fi

venv: ## Create .venv and install the development dependencies
	python3 -m venv .venv
	.venv/bin/pip install -q --upgrade pip
	.venv/bin/pip install -q -r requirements-dev.txt
	@echo "  venv ready: $(PYTHON)"

seed: ## Generate the demo source CSVs into data/raw/
	$(PYTHON) scripts/generate_data.py

# -----------------------------------------------------------------------------
#  Environment lifecycle
# -----------------------------------------------------------------------------
up: ## Start the whole infrastructure (PostgreSQL + Airflow)
	@test -f .env || { echo "  .env missing - run `make init` first"; exit 1; }
	$(COMPOSE) up -d --wait --wait-timeout 300
	@echo ""
	@echo "  Infrastructure ready."
	@echo "  Airflow  : http://localhost:$(AIRFLOW_WEB_PORT)  ($(AIRFLOW_ADMIN_USER) / voir .env)"
	@echo "  Warehouse: localhost:$(WAREHOUSE_HOST_PORT)  base=$(POSTGRES_DB)"
	@$(MAKE) --no-print-directory ps

down: ## Stop the containers (the data is kept)
	$(COMPOSE) down

restart: ## Restart the containers
	$(COMPOSE) restart

ps: ## Show the container status
	$(COMPOSE) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

logs: ## Follow the logs of every service (Ctrl+C to quit)
	$(COMPOSE) logs -f --tail=100

psql: ## Open a SQL session on the warehouse
	$(COMPOSE) exec postgres-warehouse psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

tools: ## Start Adminer, a web SQL client
	$(COMPOSE) --profile tools up -d adminer
	@echo "  Adminer : http://localhost:$(ADMINER_PORT)"
	@echo "  Server=postgres-warehouse  Database=$(POSTGRES_DB)  User=$(POSTGRES_USER)"

# -----------------------------------------------------------------------------
#  Pipeline
# -----------------------------------------------------------------------------
run-local: ## Run the ETL pipeline from your machine (outside Airflow)
	@POSTGRES_HOST=localhost POSTGRES_PORT=$(WAREHOUSE_HOST_PORT) \
	$(PYTHON) scripts/run_pipeline.py

airflow: ## Open the Airflow UI in the browser
	@echo "  http://localhost:$(AIRFLOW_WEB_PORT)"
	@xdg-open "http://localhost:$(AIRFLOW_WEB_PORT)" 2>/dev/null || true

airflow-logs: ## Follow the Airflow scheduler logs
	$(COMPOSE) logs -f --tail=100 airflow-scheduler

unpause: ## Activate the DAG (it will then start at 01:00 UTC)
	$(COMPOSE) exec -T airflow-scheduler airflow dags unpause ecommerce_daily_etl

trigger: ## Trigger an immediate DAG run
	$(COMPOSE) exec -T airflow-scheduler airflow dags trigger ecommerce_daily_etl
	@echo "  Follow the run: http://localhost:$(AIRFLOW_WEB_PORT)"

backfill: ## Replay the DAG over a period (FROM=YYYY-MM-DD TO=YYYY-MM-DD)
	@test -n "$(FROM)" || { echo "  Usage: make backfill FROM=2026-09-15 TO=2026-09-19"; exit 1; }
	$(COMPOSE) exec -T airflow-scheduler \
	airflow backfill create --dag-id ecommerce_daily_etl \
	--from-date $(FROM) --to-date $(TO)

# -----------------------------------------------------------------------------
#  dbt
# -----------------------------------------------------------------------------
dbt-run: ## Build the dbt models (staging + analytics)
	$(DBT) run --profiles-dir . --target dev"

dbt-test: ## Run the dbt quality tests
	$(DBT) test --profiles-dir . --target dev"

dbt-docs: ## Generate and serve the dbt documentation (port 8085)
	$(DBT) docs generate --profiles-dir . --target dev"
	@echo "  Documentation generated in dbt/ecommerce_dbt/target/"

# -----------------------------------------------------------------------------
#  Code quality
# -----------------------------------------------------------------------------
test: ## Run every pytest test
	@POSTGRES_HOST=localhost POSTGRES_PORT=$(WAREHOUSE_HOST_PORT) \
	$(PYTHON) -m pytest

test-unit: ## Run only the unit tests (no database needed)
	$(PYTHON) -m pytest -m "not integration"

test-integration: ## Run only the integration tests (a database is required)
	@POSTGRES_HOST=localhost POSTGRES_PORT=$(WAREHOUSE_HOST_PORT) \
	$(PYTHON) -m pytest -m integration

lint: ## Check the code style
	.venv/bin/ruff check src/ dags/ scripts/ tests/
	.venv/bin/ruff format --check src/ dags/ scripts/ tests/

# -----------------------------------------------------------------------------
#  Teaching demos
# -----------------------------------------------------------------------------
demo-idempotency: ## Prove idempotency: two runs, the same result
	@bash scripts/demo_idempotency.sh

demo-failures: ## Simulate three failures and show the error messages
	@bash scripts/demo_failures.sh

# -----------------------------------------------------------------------------
#  Reset
# -----------------------------------------------------------------------------
reset: ## DESTROY both databases and recreate them empty (replays the init scripts)
	@echo "  This deletes ALL the data in both databases."
	@read -p "  Confirm? [y/N] " ok && [ "$$ok" = "y" ] || exit 1
	$(COMPOSE) down -v
	@$(MAKE) --no-print-directory up

clean: ## Remove the Python caches and the dbt artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf dbt/ecommerce_dbt/target dbt/ecommerce_dbt/logs 2>/dev/null || true
	@echo "  Caches supprimes."
