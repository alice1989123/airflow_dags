from airflow import DAG
import types

from airflow.providers.cncf.kubernetes.secret import Secret
from datetime import datetime, timedelta
import sys
#from dotenv import dotenv_values
if 'http' in sys.modules:
    if not isinstance(sys.modules['http'], types.ModuleType) or not hasattr(sys.modules['http'], 'HTTPStatus'):
        del sys.modules['http']

from http import HTTPStatus  # Importación correcta del estándar

# -- Importación del operador una vez corregido el path
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator



env_secret = Secret(
    deploy_type='env',          # inject as environment variables
    deploy_target=None,         # match keys as is
    secret='db-creds'         
)


default_args = {
    "owner": "alice",
    "start_date": datetime(2024, 1, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="klines_etl_k8s_file",
    default_args=default_args,
    schedule="@hourly",
    catchup=False,
    tags=["crypto", "k8s" ,"gatsbyt"],
) as dag:

    run_scraper = KubernetesPodOperator(
    task_id="run_klines_etl_pod",
    namespace="production",
    name="klines_etl",
    image="registry-docker-registry.registry.svc.cluster.local:5000/klines-etl:latest",
    secrets=[env_secret],
    is_delete_operator_pod=True,
    execution_timeout=timedelta(minutes=15),
    startup_timeout_seconds=900,
    get_logs=True,
    cmds=["/bin/bash", "-c"],
    arguments=["cd /app && ./backfill_runner.sh"],
)