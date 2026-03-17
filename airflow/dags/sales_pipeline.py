"""
sales_pipeline.py — Three-layer medallion architecture pipeline.

Loads raw CSV data into bronze tables, transforms through silver and gold
layers using dbt, and runs data quality tests.

DAG structure:
    ingest_raw_sales ──────────► run_dbt_silver_sales ──┐
                                                        ├─► run_dbt_fct_sales ─► run_dbt_tests
    ingest_raw_customers ──────► run_dbt_silver_customers┘
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator

from failure_callback import on_task_failure


default_args = {
    "owner": "data-team",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=1),
    "on_failure_callback": on_task_failure,
}

# Paths inside the Airflow container (set by docker-compose volume mounts)
SEEDS_DIR = "/data/seeds"
DBT_DIR = "/dbt"

with DAG(
    dag_id="sales_pipeline",
    default_args=default_args,
    description="Sales data pipeline: CSV → Bronze → Silver → Gold",
    schedule=timedelta(days=1),
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["sales", "dbt", "pipeline"],
) as dag:

    # ── Bronze: Load CSVs into bronze tables ──────────────────

    ingest_raw_sales = BashOperator(
        task_id="ingest_raw_sales",
        bash_command=(
            f"python /opt/airflow/dags/scripts/load_csv.py "
            f"bronze.sales {SEEDS_DIR}/raw_sales.csv"
        ),
    )

    ingest_raw_customers = BashOperator(
        task_id="ingest_raw_customers",
        bash_command=(
            f"python /opt/airflow/dags/scripts/load_csv.py "
            f"bronze.customers {SEEDS_DIR}/raw_customers.csv"
        ),
    )

    # ── Silver: Transform with dbt ────────────────────────────

    run_dbt_silver_sales = BashOperator(
        task_id="run_dbt_silver_sales",
        bash_command=(
            f"dbt run --project-dir {DBT_DIR} --profiles-dir {DBT_DIR} "
            f"--select silver_sales"
        ),
    )

    run_dbt_silver_customers = BashOperator(
        task_id="run_dbt_silver_customers",
        bash_command=(
            f"dbt run --project-dir {DBT_DIR} --profiles-dir {DBT_DIR} "
            f"--select silver_customers"
        ),
    )

    # ── Gold: Aggregate with dbt ──────────────────────────────

    run_dbt_fct_sales = BashOperator(
        task_id="run_dbt_fct_sales",
        bash_command=(
            f"dbt run --project-dir {DBT_DIR} --profiles-dir {DBT_DIR} "
            f"--select fct_sales"
        ),
    )

    # ── Tests: Run dbt tests ──────────────────────────────────

    run_dbt_tests = BashOperator(
        task_id="run_dbt_tests",
        bash_command=(
            f"dbt test --project-dir {DBT_DIR} --profiles-dir {DBT_DIR}"
        ),
    )

    # ── Task dependencies ─────────────────────────────────────

    ingest_raw_sales >> run_dbt_silver_sales
    ingest_raw_customers >> run_dbt_silver_customers
    [run_dbt_silver_sales, run_dbt_silver_customers] >> run_dbt_fct_sales
    run_dbt_fct_sales >> run_dbt_tests