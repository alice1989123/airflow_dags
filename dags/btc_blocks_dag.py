from datetime import datetime, timedelta
import sys
import types

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.cncf.kubernetes.secret import Secret
from kubernetes.client import models as k8s

if "http" in sys.modules:
    http_module = sys.modules["http"]
    if not isinstance(http_module, types.ModuleType) or not hasattr(
        http_module, "HTTPStatus"
    ):
        del sys.modules["http"]

ETL_IMAGE = (
    "390402534126.dkr.ecr.us-east-1.amazonaws.com/"
    "bitcoin-etl@sha256:1db07527fa436f15e414b6886d1738f0938e21f6aaf65c71aef159a9915b4805"
)
ETL_NAMESPACE = "gatsbyt"
ETL_SECRET = Secret(
    deploy_type="env",
    deploy_target=None,
    secret="btc-etl-env",
)

ETL_VOLUMES = [
    k8s.V1Volume(
        name="btc-output",
        host_path=k8s.V1HostPathVolumeSource(
            path="/srv/btc-etl/output",
            type="Directory",
        ),
    ),
    k8s.V1Volume(
        name="btc-state",
        host_path=k8s.V1HostPathVolumeSource(
            path="/srv/btc-etl/state",
            type="Directory",
        ),
    ),
]

ETL_VOLUME_MOUNTS = [
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

METRICS_VOLUMES = ETL_VOLUMES + [
    k8s.V1Volume(
        name="metrics-runner",
        config_map=k8s.V1ConfigMapVolumeSource(
            name="bitcoin-metrics-runner",
            default_mode=0o555,
        ),
    ),
]

METRICS_VOLUME_MOUNTS = ETL_VOLUME_MOUNTS + [
    k8s.V1VolumeMount(
        name="metrics-runner",
        mount_path=(
            "/recovery/bitcoin-daily-onchain-metrics-optimized.py"
        ),
        sub_path="bitcoin-daily-onchain-metrics-optimized.py",
        read_only=True,
    ),
]

DEFAULT_ARGS = {
    "owner": "alice",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

BLOCK_EVENTS_RESOURCES = k8s.V1ResourceRequirements(
    requests={"cpu": "2", "memory": "18Gi"},
    limits={"cpu": "4", "memory": "24Gi"},
)

DAILY_METRICS_RESOURCES = k8s.V1ResourceRequirements(
    requests={"cpu": "2", "memory": "18Gi"},
    limits={"cpu": "6", "memory": "24Gi"},
)

with DAG(
    dag_id="bitcoin_block_events_incremental",
    default_args=DEFAULT_ARGS,
    schedule="*/15 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["bitcoin", "etl", "incremental"],
) as block_events_dag:
    KubernetesPodOperator(
        task_id="block_events_incremental",
        name="bitcoin-block-events-incremental",
        namespace=ETL_NAMESPACE,
        image=ETL_IMAGE,
        image_pull_policy="IfNotPresent",
        cmds=["python3"],
        arguments=["/app/etl/block_events_incremental.py"],
        env_vars={
            "ENV": "dev",
            "LOG_LEVEL": "INFO",
            "BLOCK_EVENTS_BATCH": "1000",
        },
        secrets=[ETL_SECRET],
        container_resources=BLOCK_EVENTS_RESOURCES,
        volumes=ETL_VOLUMES,
        volume_mounts=ETL_VOLUME_MOUNTS,
        node_selector={"kubernetes.io/hostname": "alice-server"},
        get_logs=True,
        is_delete_operator_pod=True,
        startup_timeout_seconds=600,
        execution_timeout=timedelta(minutes=30),
        do_xcom_push=False,
    )

with DAG(
    dag_id="bitcoin_daily_onchain_metrics",
    default_args=DEFAULT_ARGS,
    schedule="30 1 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["bitcoin", "analytics", "daily"],
) as daily_metrics_dag:
    KubernetesPodOperator(
        task_id="daily_onchain_metrics",
        name="bitcoin-daily-onchain-metrics",
        namespace=ETL_NAMESPACE,
        image=ETL_IMAGE,
        image_pull_policy="IfNotPresent",
        cmds=["python3"],
        arguments=[
            "/recovery/bitcoin-daily-onchain-metrics-optimized.py"
        ],
        env_vars={
            "ENV": "dev",
            "LOG_LEVEL": "INFO",
        },
        secrets=[ETL_SECRET],
        container_resources=DAILY_METRICS_RESOURCES,
        volumes=METRICS_VOLUMES,
        volume_mounts=METRICS_VOLUME_MOUNTS,
        node_selector={"kubernetes.io/hostname": "alice-server"},
        get_logs=True,
        is_delete_operator_pod=True,
        startup_timeout_seconds=600,
        execution_timeout=timedelta(hours=2),
        do_xcom_push=False,
    )
