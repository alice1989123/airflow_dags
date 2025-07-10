from airflow import DAG
import types

from airflow.kubernetes.secret import Secret
from airflow.kubernetes.volume import Volume
from airflow.kubernetes.volume_mount import VolumeMount
from datetime import datetime, timedelta
import sys
#from dotenv import dotenv_values
if 'http' in sys.modules:
    if not isinstance(sys.modules['http'], types.ModuleType) or not hasattr(sys.modules['http'], 'HTTPStatus'):
        del sys.modules['http']

from http import HTTPStatus  # Importación correcta del estándar

# -- Importación del operador una vez corregido el path
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator



default_args = {
    "owner": "alice",
    "start_date": datetime(2024, 1, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Mount the file to /run/secrets/.env
secret_file_mount = Secret(
    deploy_type="volume",
    deploy_target="/run/secrets/.env",
    secret="crypto-env-file",
    key="env_file"   # <- matches the key name from --from-file
)

with DAG(
    dag_id="crypto_news_scraper_k8s_file",
    default_args=default_args,
    schedule="@hourly",
    catchup=False,
    tags=["crypto", "k8s"],
) as dag:

    run_scraper = KubernetesPodOperator(
        task_id="run_scraper_pod",
        namespace="production",
        name="crypto-scraper",
        image="registry-docker-registry.registry.svc.cluster.local:5000/crypto_news_scrapper:latest",
        cmds=["python", "main.py"],
        secrets=[secret_file_mount],
        is_delete_operator_pod=True,
        image_pull_secrets=[{"name": "docker-credentials"}],  # optional
        env_vars={
            "ENV_FILE": "/run/secrets/.env"
        },
    )