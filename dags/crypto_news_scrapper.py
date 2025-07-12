from airflow import DAG
import types

from airflow.providers.cncf.kubernetes.secret import Secret
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



env_secret = Secret(
    deploy_type='env',          # inject as environment variables
    deploy_target=None,         # match keys as is
    secret='crypto-env'         # name of the secret you created
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
        secrets=[env_secret],
        is_delete_operator_pod=True,
        image_pull_secrets=[{"name": "docker-credentials"}],  # optional
       
    )