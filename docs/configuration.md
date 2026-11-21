# Configuration

Environment variables read by the project. Copy `.env.example` to `.env`
and adjust the values; `.env` is git-ignored and must never be committed.

| Variable | Example value | Notes |
|---|---|---|
| `POSTGRES_HOST` | `postgres-warehouse` | 1. WAREHOUSE - the database holding the e-commerce data HOST and PORT are the values as seen FROM INSIDE the Docker network.… |
| `POSTGRES_PORT` | `5432` | — |
| `POSTGRES_DB` | `ecommerce` | — |
| `POSTGRES_USER` | `ecommerce` | — |
| `POSTGRES_PASSWORD` | *(secret — choose your own)* | — |
| `WAREHOUSE_HOST_PORT` | `5435` | Port published on YOUR machine to connect from outside (DBeaver, a local psql, Adminer). 5435 avoids the other projects already running on… |
| `AIRFLOW_DB_NAME` | `airflow` | 2. METADATA DB - Airflow's internal database Airflow stores its DAG runs, task instances, logs, users and connections there. It is… |
| `AIRFLOW_DB_USER` | `airflow` | — |
| `AIRFLOW_DB_PASSWORD` | *(secret — choose your own)* | — |
| `AIRFLOW_UID` | `50000` | 3. AIRFLOW - arrives in PHASE 5 AIRFLOW_UID: the Unix UID the Airflow containers run as. Without it, the files written into ./logs and… |
| `AIRFLOW_WEB_PORT` | `8089` | — |
| `ADMINER_PORT` | `8083` | 4. OPTIONAL TOOLS Adminer: a web SQL client, started only with --profile tools |
| `AIRFLOW_FERNET_KEY` | *(secret — choose your own)* | 5. AIRFLOW - security and administrator account FERNET_KEY encrypts the Connection passwords in the metadata db. Generate your own: python3… |
| `AIRFLOW_JWT_SECRET` | *(secret — choose your own)* | Signing secret for the internal API tokens: python3 -c "import secrets; print(secrets.token_hex(32))" |
| `AIRFLOW_ADMIN_USER` | `admin` | — |
| `AIRFLOW_ADMIN_PASSWORD` | *(secret — choose your own)* | — |
