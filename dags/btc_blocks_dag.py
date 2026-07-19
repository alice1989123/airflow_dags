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
from kubernetes.client import models as k8s

from datetime import datetime, timedelta

default_args = {
    "owner": "alice",
    "retries": 3,
    "retry_delay": timedelta(seconds=30),
}

# --- Secrets: map secretKeyRef -> env vars ---
env_secret = Secret(
    deploy_type='env',          # inject as environment variables
    deploy_target=None,         # match keys as is
    secret='btc-etl-env'         # name of the secret you created
)

# --- Volumes (hostPath) ---
volumes = [
    k8s.V1Volume(
        name="btc-output",
        host_path=k8s.V1HostPathVolumeSource(
            path="/srv/btc-etl/output",
            type="DirectoryOrCreate",
        ),
    ),
    k8s.V1Volume(
        name="btc-state",
        host_path=k8s.V1HostPathVolumeSource(
            path="/srv/btc-etl/state",
            type="DirectoryOrCreate",
        ),
    ),
]

volume_mounts = [
    k8s.V1VolumeMount(
        name="btc-output",
        mount_path="/srv/btc-etl/output",
        read_only=False,
    ),
    k8s.V1VolumeMount(
        name="btc-state",
        mount_path="/srv/btc-etl/state",
        read_only=False,
    ),
]

# --- Resources (requests/limits) ---
container_resources = k8s.V1ResourceRequirements(
    requests={"cpu": "500m", "memory": "2Gi"},
    limits={"cpu": "2", "memory": "4Gi"},
)

with DAG(
    dag_id="bitcoin_block_events_incremental",
    default_args=default_args,
    schedule="0 0 * * *",     # same as your CronJob
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,           # CronJob concurrencyPolicy: Forbid
) as dag:

    block_events = KubernetesPodOperator(
        task_id="block_events_incremental",
        name="bitcoin-block-events-incremental",
        namespace="production",

        image="390402534126.dkr.ecr.us-east-1.amazonaws.com/bitcoin-etl@sha256:1db07527fa436f15e414b6886d1738f0938e21f6aaf65c71aef159a9915b4805",
        image_pull_policy="IfNotPresent",

        cmds=["python3"],
        arguments=["/app/etl/block_events_incremental.py"],

        env_vars={
            "ENV": "dev",
            "LOG_LEVEL": "INFO",
            "BLOCK_EVENTS_BATCH": "100",
        },

        secrets=[env_secret],
        container_resources=container_resources,

        volumes=volumes,
        volume_mounts=volume_mounts,

        node_selector={"kubernetes.io/hostname": "alice-server"},

        get_logs=True,
        is_delete_operator_pod=True,
        startup_timeout_seconds=600,
        do_xcom_push=False,
    )

    daily_metrics = KubernetesPodOperator(
    task_id="daily_onchain_metrics",
    name="bitcoin-daily-onchain-metrics",
    namespace="production",

    image="390402534126.dkr.ecr.us-east-1.amazonaws.com/bitcoin-etl@sha256:1db07527fa436f15e414b6886d1738f0938e21f6aaf65c71aef159a9915b4805",
    image_pull_policy="IfNotPresent",

    cmds=["python3"],
    arguments=["/app/etl/daily_onchain_metrics_spark.py"],

    env_vars={
        "ENV": "dev",
        "LOG_LEVEL": "INFO",
        # add any metric params here if you have them
    },

    secrets=[env_secret],
    container_resources=container_resources,

    volumes=volumes,
    volume_mounts=volume_mounts,

    node_selector={"kubernetes.io/hostname": "alice-server"},

    get_logs=True,
    is_delete_operator_pod=True,
    startup_timeout_seconds=600,
    do_xcom_push=False,
)
    
    block_events >> daily_metrics
