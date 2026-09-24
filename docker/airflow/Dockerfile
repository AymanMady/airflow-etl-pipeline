# =============================================================================
#  The project's Airflow image
# =============================================================================
#  We start from the official image and add only what the pipeline needs. You
#  NEVER build an Airflow image from scratch: the official one carries dozens of
#  settings (user, entrypoint, permissions) that would be reproduced badly.
# =============================================================================
FROM apache/airflow:3.3.2

# -----------------------------------------------------------------------------
#  1. ETL pipeline dependencies
# -----------------------------------------------------------------------------
#  They are installed into Airflow's Python environment: the code in src/ runs
#  directly inside the tasks.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# -----------------------------------------------------------------------------
#  2. dbt, in a SEPARATE virtual environment
# -----------------------------------------------------------------------------
#  Why not simply `pip install dbt-core` next to Airflow?
#
#  Because the two projects pin different versions of the same libraries
#  (Jinja2, click, protobuf...). Installing them together forces pip to find a
#  compromise, and sooner or later that compromise breaks one of them - with an
#  incomprehensible error at the worst possible moment.
#
#  The standard solution: dbt in its own venv, invoked by its absolute path
#  (/opt/dbt_venv/bin/dbt) from a BashOperator. No dependency is shared, so no
#  conflict is possible.
USER root
RUN python3 -m venv /opt/dbt_venv \
    && /opt/dbt_venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/dbt_venv/bin/pip install --no-cache-dir "dbt-core>=1.9,<2.0" "dbt-postgres>=1.9,<2.0" \
    && chmod -R a+rX /opt/dbt_venv
USER airflow

# -----------------------------------------------------------------------------
#  3. Make `src` importable from the DAGs
# -----------------------------------------------------------------------------
#  Without this, `from src.extract.extract import extract_all` would fail:
#  Python does not look in /opt/airflow automatically.
ENV PYTHONPATH=/opt/airflow
