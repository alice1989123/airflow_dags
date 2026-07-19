from airflow import DAG
from airflow.utils.task_group import TaskGroup
from airflow.providers.cncf.kubernetes.secret import Secret
from airflow.decorators import task                     # NEW
from airflow.models import Variable 
from airflow.providers.postgres.hooks.postgres import PostgresHook
import types
import sys
import json, re 
# ---- keep this shim (KPO + http bug workaround) ----
if 'http' in sys.modules:
    if not isinstance(sys.modules['http'], types.ModuleType) or not hasattr(sys.modules['http'], 'HTTPStatus'):
        del sys.modules['http']
from http import HTTPStatus  # DO NOT REMOVE
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
# ----------------------------------------------------
from airflow.exceptions import AirflowSkipException
from datetime import datetime, timedelta

# -------- secrets (K8s Secrets) --------

db_secret = Secret(deploy_type='env', deploy_target=None, secret='db-creds')
env_secret_aws = Secret(deploy_type='env', deploy_target=None, secret='aws-credentials-dynamo')
env_secret_mlflow = Secret(deploy_type='env', deploy_target=None, secret='mlflow-credentials')
env_telegram = Secret(deploy_type='env', deploy_target=None, secret='telegram')


# --------  dynamic coin resolution + arg builders --------
def _parse_coins(val):
    if val is None:
        return []
    if isinstance(val, list):
        seq = val
    elif isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        seq = json.loads(s) if s.startswith('[') else re.split(r'[,\s]+', s)
    else:
        return []
    out, seen = [], set()
    for x in seq:
        c = str(x).strip().upper()
        if c and c not in seen:
            seen.add(c); out.append(c)
    return out
@task
def resolve_coins(param_coins=None) -> list[str]:
    """
    Priority:
      1) DAG param `coins` (list or CSV/JSON string)
      2) Airflow Variable CRYPTO_COINS (CSV or JSON)
      3) Postgres (coin_catalog.tracked = true) via conn_id 'crypto_db'
    """
    coins = _parse_coins(param_coins)
    if not coins:
        coins = _parse_coins(Variable.get("CRYPTO_COINS", default_var=""))

    if not coins:
        hook = PostgresHook(postgres_conn_id="crypto_db")
        rows = hook.get_records("SELECT symbol FROM coin_catalog WHERE tracked = true")
        coins = [r[0].strip().upper() for r in rows if r and r[0]]

    # final de-dup & sanity
    coins = [c for i, c in enumerate(coins) if c and c not in coins[:i]]

    if not coins:
        # you can default instead of skipping if you prefer:
        # return ["BTCUSDT","ETHUSDT","SOLUSDT"]
        raise AirflowSkipException("No coins resolved from params/Variable/DB")

    return coins
@task
def to_forecast_args(coins: list[str]) -> list[list[str]]:
    return [["generate_predictions.py", "--symbol", c ,"--interval", "1h"] for c in coins]

@task
def to_strategy_args(coins: list[str]) -> list[list[str]]:
    return [[f"cd /app && ./runner.sh --symbol {c}"] for c in coins]
# -------------------------------------------------------------

with DAG(
    "crypto_hourly",
    start_date=datetime(2024, 1, 1),
    schedule="5 * * * *",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["crypto", "k8s", "gatsbyt"],
    params={"coins": None},
) as dag:
    coins = resolve_coins(dag.params.get("coins", None))
    forecast_args = to_forecast_args(coins)
    strategy_args = to_strategy_args(coins)

    with TaskGroup("etl") as etl:
        etl_1h = KubernetesPodOperator(
            task_id="etl_1h",
            namespace="gatsbyt",
            image="390402534126.dkr.ecr.us-east-1.amazonaws.com/klines-etl@sha256:0af2df904835fd3b4ebf019c4091897d8eb723d5da92958936b064a79e4a9f99",
            secrets=[db_secret],
            is_delete_operator_pod=True,
            execution_timeout=timedelta(minutes=15),
            startup_timeout_seconds=300,
            get_logs=True,
            cmds=["/bin/bash", "-c"],
            arguments=["cd /app && TIMEFRAME=1h ./etl_runner.sh"],
        )

    with TaskGroup("forecast") as forecast:
        forecast_task = (
            KubernetesPodOperator.partial(
                task_id="predict",
                namespace="gatsbyt",
                image="390402534126.dkr.ecr.us-east-1.amazonaws.com/btc_forecast@sha256:32afc9d6f2e4c654842935524398c25a3f1d10ceaaf8265588d0afd0bb363be5",
                secrets=[db_secret, env_secret_aws, env_secret_mlflow],
                is_delete_operator_pod=True,
                execution_timeout=timedelta(minutes=15),
                startup_timeout_seconds=900,
                get_logs=True,
                cmds=["python3.11"],
            )
            .expand(arguments=forecast_args)
        )

    with TaskGroup("strategies") as strategies:
        strat_task = (
            KubernetesPodOperator.partial(
                task_id="run_crypto_strategies_pod",
                namespace="gatsbyt",
                image="390402534126.dkr.ecr.us-east-1.amazonaws.com/crypto-strategies@sha256:50a07053d94c7945c4ebe52602e87a96d3c5c67b324a75f49264067bc5341601",
                secrets=[db_secret, env_secret_aws, env_telegram],
                is_delete_operator_pod=True,
                execution_timeout=timedelta(minutes=15),
                startup_timeout_seconds=900,
                env_vars={"PYTHONPATH": "/app"},
                get_logs=True,
                cmds=["/bin/bash", "-c"],
            )
            .expand(arguments=strategy_args)
        )

    with TaskGroup("tracker") as tracker:
        track_task = KubernetesPodOperator(
            task_id="run_signal_tracker_pod",
            namespace="gatsbyt",
            image="390402534126.dkr.ecr.us-east-1.amazonaws.com/signal-tracker@sha256:b716a19f321a8f287e9efb6278684791604f72694dbfe885cc26ea959fedf660",
            secrets=[db_secret, env_secret_aws, env_telegram],
            is_delete_operator_pod=True,
            execution_timeout=timedelta(minutes=15),
            startup_timeout_seconds=900,
            get_logs=True,
            cmds=["python"],
            arguments=["main.py"],
        )

    etl >> forecast >> strategies >> tracker
