from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
#from airflow.kubernetes.secret import Secret
from airflow.kubernetes.volume import Volume
from airflow.kubernetes.volume_mount import VolumeMount
from datetime import datetime, timedelta
from dotenv import dotenv_values

# ──────────────────────────────────────────────────────────────
# 1️⃣  Load env-vars from local file and pass them as dict
#     (alternatively mount the file in the pod – see comment below)
env_vars = dotenv_values("/home/alice/crypto_news_scrapper/.env_docker.env")

default_args = {
    "owner": "alice",
    "depends_on_past": False,
    "email": ["aliciabasilo.ab@gmail.com"],
    "email_on_failure": True,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "start_date": datetime(2024, 1, 1),
}

with DAG(
    dag_id="crypto_news_scraper_k8s",
    default_args=default_args,
    schedule="@hourly",
    catchup=False,
    tags=["crypto", "k8s"],
) as dag:

    run_scraper = KubernetesPodOperator(
        task_id="run_scraper_pod",
        # 2️⃣  Image in your private registry
        image="registry-docker-registry.registry.svc.cluster.local:5000/crypto_news_scrapper:latest",
        namespace="production",              # or your airflow namespace
        name="crypto-scraper",
        cmds=["python", "main.py"],       # entrypoint if image CMD isn’t enough
        env_vars=env_vars,                # inject all .env vars
        # 3️⃣  Authenticate to registry (imagePullSecrets)
        #image_pull_secrets=[{"name": "docker-credentials"}],
        # 4️⃣  Delete pod on success to save cluster resources
        is_delete_operator_pod=True,
        # 5️⃣  If you need network-policy exceptions or node selectors:
        #      affinity=..., tolerations=..., node_selector=...
        # 6️⃣  If your .env file must be mounted instead of env-injected:
        #      volume_mounts=[VolumeMount('env', '/run/secrets/.env', None, False)],
        #      volumes=[Volume('env', Secret('my-env-secret', 'env_file'))],
    )
