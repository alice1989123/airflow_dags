import sys
import types
from datetime import datetime
from airflow import DAG
from airflow.models import Variable
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

    image_tag = Variable.get("SECURITY_UPDATER_IMAGE_TAG", default_var="latest")

    run_updater =KubernetesPodOperator(
            task_id='run_updater',
            name='security-updater',
            namespace='production',
            image='registry.local:31504/security_group_updater:latest',
            cmds=['python'],
            arguments=['security_group_updater.py'],
            image_pull_policy='Always',
            env_from=[
                V1EnvFromSource(secret_ref=V1SecretEnvSource(name='aws-creds-secret'))
            ],
            is_delete_operator_pod=True,
            get_logs=True,
    )


# kubectl cp ~/airflow/dags/security_updater_dag.py airflow/dag-uploader:/dags/security_updater_dag.py