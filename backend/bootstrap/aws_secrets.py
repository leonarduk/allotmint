"""Load secrets from AWS Secrets Manager into environment variables.

This module must be imported (and ``load_aws_secrets_to_env`` called) before
any backend module that reads ``os.environ`` at import time, such as
``backend.auth``.  The handler entry-point calls this first so that
``JWT_SECRET`` and ``GOOGLE_CLIENT_ID`` are in ``os.environ`` before
``backend.app`` is imported.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_ENV_MAPPING: dict[str, str] = {
    "jwt_secret": "JWT_SECRET",
    "google_client_id": "GOOGLE_CLIENT_ID",
}


def load_aws_secrets_to_env(
    secret_name: str | None = None,
) -> None:
    """Fetch the named Secrets Manager secret and inject values as env vars.

    Only runs when ``APP_ENV`` is ``aws`` or ``production``.  Values that are
    already present in ``os.environ`` are not overwritten so that explicit env
    vars always win.

    Missing or non-JSON secrets are logged and silently skipped; the app will
    fail with its own validation errors later if required values are absent.
    """

    app_env = os.getenv("APP_ENV", "")
    if app_env not in {"aws", "production"}:
        return

    if secret_name is None:
        secret_name = os.getenv("APP_SECRET_NAME", "allotmint/app")

    try:
        import boto3  # type: ignore[import-untyped]

        client = boto3.client("secretsmanager", region_name=os.getenv("APP_REGION") or os.getenv("AWS_REGION"))
        response = client.get_secret_value(SecretId=secret_name)
        secret_string = response.get("SecretString") or ""
        secret_data: dict = json.loads(secret_string)
    except ImportError:
        logger.warning("boto3 not available; cannot load secrets from AWS Secrets Manager")
        return
    except json.JSONDecodeError as exc:
        logger.error("Secret %s is not valid JSON: %s", secret_name, exc)
        return
    except Exception as exc:
        logger.error("Failed to load secret %s from Secrets Manager: %s", secret_name, exc)
        return

    for secret_key, env_var in _ENV_MAPPING.items():
        if env_var not in os.environ and secret_key in secret_data:
            value = secret_data[secret_key]
            if isinstance(value, str) and value:
                os.environ[env_var] = value
                logger.debug("Injected %s from Secrets Manager", env_var)
