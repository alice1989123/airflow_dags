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


from datetime import datetime, timedelta
default_args = {
    "owner": "alice",
    "retries": 3,
    "retry_delay": timedelta(seconds=30),
}

with DAG(
    "btc_export_blocks",
    default_args=default_args,
    schedule_interval="*/1 * * * *",   # every 1 min
    start_date=datetime(2025, 1, 1),
    catchup=False,
) as dag:

    export_blocks = KubernetesPodOperator(
        name="btc-block-export",
        image="alice/btc-etl:latest",   # build this Docker image
        cmds=["python"],
        arguments=["etl/extract/blocks_incremental.py"],
        namespace="airflow",
        get_logs=True,
        is_delete_operator_pod=True,
    )