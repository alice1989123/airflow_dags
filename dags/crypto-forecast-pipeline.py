from airflow import DAG
from airflow.utils.task_group import TaskGroup
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.cncf.kubernetes.secret import Secret
import types
import sys

# ---- keep this shim (KPO + http bug workaround) ----
if 'http' in sys.modules:
    if not isinstance(sys.modules['http'], types.ModuleType) or not hasattr(sys.modules['http'], 'HTTPStatus'):
        del sys.modules['http']
from http import HTTPStatus  # DO NOT REMOVE
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
# ----------------------------------------------------

from datetime import datetime, timedelta

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

db_secret = Secret(deploy_type='env', deploy_target=None, secret='db-creds')
env_secret_aws = Secret(deploy_type='env', deploy_target=None, secret='aws-credentials-dynamo')
env_secret_mlflow = Secret(deploy_type='env', deploy_target=None, secret='mlflow-credentials')
env_telegram = Secret(deploy_type='env', deploy_target=None, secret='telegram')

with DAG(
    "crypto_hourly",
    start_date=datetime(2024, 1, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["crypto", "k8s", "gatsbyt"],
) as dag:

    # A) ETL
    with TaskGroup("etl") as etl:
        etl_task = KubernetesPodOperator(
            task_id="run_klines_etl_pod",
            namespace="production",
            name="klines_etl",
            image="registry-docker-registry.registry.svc.cluster.local:5000/klines-etl:latest",
            secrets=[db_secret],
            is_delete_operator_pod=True,
            execution_timeout=timedelta(minutes=15),
            startup_timeout_seconds=900,
            get_logs=True,
            cmds=["/bin/bash", "-c"],
            arguments=["cd /app && ./backfill_runner.sh"],
        )

    # B) Forecast (mapped per coin)
    with TaskGroup("forecast") as forecast:
        forecast_task = (
            KubernetesPodOperator.partial(
                task_id="predict",
                namespace="production",
                name="btc_forecast",
                image="registry-docker-registry.registry.svc.cluster.local:5000/btc_forecast:latest",
                secrets=[db_secret, env_secret_aws, env_secret_mlflow],
                is_delete_operator_pod=True,
                execution_timeout=timedelta(minutes=15),
                startup_timeout_seconds=900,
                get_logs=True,
                cmds=["python3.11"],
            )
            .expand(arguments=[["generate_predictions.py", "--symbol", c] for c in COINS])
        )

    # C) Strategies (mapped per coin)
    with TaskGroup("strategies") as strategies:
        strat_task = (
            KubernetesPodOperator.partial(
                task_id="run_crypto_strategies_pod",
                namespace="production",
                name="crypto-strategies",
                image="registry-docker-registry.registry.svc.cluster.local:5000/crypto-strategies:latest",
                secrets=[db_secret, env_secret_aws, env_telegram],
                is_delete_operator_pod=True,
                execution_timeout=timedelta(minutes=15),
                startup_timeout_seconds=900,
                env_vars={"PYTHONPATH": "/app"},
                get_logs=True,
                cmds=["/bin/bash", "-c"],  # needed for inline script
            )
            .expand(arguments=[["cd /app && ./runner.sh --symbol " + c] for c in COINS])
        )

    # D) Tracker (single task; map later if you split tracking per-coin)
    with TaskGroup("tracker") as tracker:
        track_task = KubernetesPodOperator(
            task_id="run_signal_tracker_pod",
            namespace="production",
            name="signal-tracker",
            image="registry-docker-registry.registry.svc.cluster.local:5000/signal-tracker:latest",
            secrets=[db_secret, env_secret_aws, env_telegram],
            is_delete_operator_pod=True,
            execution_timeout=timedelta(minutes=15),
            startup_timeout_seconds=900,
            get_logs=True,
            cmds=["python"],
            arguments=["main.py"],
        )

    etl >> forecast >> strategies >> tracker
