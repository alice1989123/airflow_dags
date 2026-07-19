import sys
import types
from datetime import datetime
from airflow import DAG
from kubernetes.client import V1EnvFromSource, V1SecretEnvSource
# -- Fix para evitar colisión con el módulo estándar 'http'
if 'http' in sys.modules:
    if not isinstance(sys.modules['http'], types.ModuleType) or not hasattr(sys.modules['http'], 'HTTPStatus'):
        del sys.modules['http']

from http import HTTPStatus  # Importación correcta del estándar

# -- Importación del operador una vez corregido el path
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

# -- Definición del DAG
with DAG(
    "security_updater",
    start_date=datetime(2024, 1, 1),
    schedule="*/5 * * * *",
    catchup=False,
    tags=["security", "kubernetes"]
) as dag:

    run_updater =KubernetesPodOperator(
            task_id='run_updater',
            name='security-updater',
            namespace='production',
            image='390402534126.dkr.ecr.us-east-1.amazonaws.com/security_group_updater@sha256:5fca77c835cb0ded5bf4d49319e80ffa06027c4b744738f0761794e244e15966',
            cmds=['python'],
            arguments=['security_group_updater.py'],
            image_pull_policy='IfNotPresent',
            env_from=[
                V1EnvFromSource(secret_ref=V1SecretEnvSource(name='aws-creds-secret'))
            ],
            is_delete_operator_pod=True,
            get_logs=True,
    )


# kubectl cp ~/airflow/dags/security_updater_dag.py airflow/dag-uploader:/dags/security_updater_dag.py
