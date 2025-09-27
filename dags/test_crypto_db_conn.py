# dags/test_crypto_db_conn.py
from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime

with DAG(
    dag_id="test_crypto_db_conn",
    start_date=datetime(2024,1,1),
    schedule=None,
    catchup=False,
) as dag:
    @task
    def ping_db():
        hook = PostgresHook(postgres_conn_id="crypto_db")
        row = hook.get_first("SELECT 1;")
        # will raise if connection/auth/SSL fails
        print("DB responded:", row)

    ping_db()
