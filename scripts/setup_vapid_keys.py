#!/usr/bin/env python3
"""Generate VAPID keys and store them in AWS Parameter Store.

The script is idempotent: if the configured parameters already exist no
changes are made.  Parameter names default to
``/allotmint/vapid/public`` and ``/allotmint/vapid/private`` but can be
customised via the ``VAPID_PUBLIC_KEY_PARAM`` and
``VAPID_PRIVATE_KEY_PARAM`` environment variables.
"""

from __future__ import annotations

import base64
import os
from typing import Tuple

import boto3
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _generate_keypair() -> Tuple[str, str]:
    """Return a new (public, private) VAPID key pair."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    raw_private = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    raw_public = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode("ascii")
    private_b64 = base64.urlsafe_b64encode(raw_private).rstrip(b"=").decode("ascii")
    return public_b64, private_b64


def main() -> None:
    public_param = os.getenv("VAPID_PUBLIC_KEY_PARAM", "/allotmint/vapid/public")
    private_param = os.getenv("VAPID_PRIVATE_KEY_PARAM", "/allotmint/vapid/private")
    ssm = boto3.client("ssm")

    try:
        ssm.get_parameter(Name=public_param)
        ssm.get_parameter(Name=private_param, WithDecryption=True)
        print("VAPID keys already exist in Parameter Store; nothing to do.")
        return
    except ClientError as exc:
        if exc.response["Error"].get("Code") != "ParameterNotFound":
            raise

    public_key, private_key = _generate_keypair()

    ssm.put_parameter(Name=public_param, Value=public_key, Type="String", Overwrite=True)
    ssm.put_parameter(
        Name=private_param,
        Value=private_key,
        Type="SecureString",
        Overwrite=True,
    )

    print(
        f"Stored VAPID key pair at {public_param} and {private_param} in Parameter Store."
    )


if __name__ == "__main__":
    main()
