"""Simple JSON storage abstraction.

The alerts module persists user thresholds and push subscription metadata as
JSON.  This file provides a tiny pluggable interface that can back the data
with a local file (for tests), an S3 object or an AWS Systems Manager
Parameter Store entry.  The storage is selected via URI scheme:

``file:///path/to/file.json``      -> local file
``s3://bucket/key.json``          -> S3 object
``ssm://parameter-name``          -> Parameter Store

Each backend quietly returns an empty dictionary on read failures to keep the
application resilient in environments where the store has not been
provisioned yet.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Protocol
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class JSONStorage(Protocol):
    """Protocol for simple JSON key-value storage."""

    def load(self) -> Dict[str, Any]:
        """Return the stored JSON object or an empty dict."""

    def save(self, data: Dict[str, Any]) -> None:
        """Persist ``data``."""


@dataclass
class FileJSONStorage:
    path: Path

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read %s: %s", self.path, exc)
            return {}

    def save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data))


@dataclass
class S3JSONStorage:
    bucket: str
    key: str
    client: Any | None = None

    def _client(self):
        if self.client is None:
            import boto3  # type: ignore

            self.client = boto3.client("s3")
        return self.client

    def load(self) -> Dict[str, Any]:
        try:
            obj = self._client().get_object(Bucket=self.bucket, Key=self.key)
            return json.loads(obj["Body"].read())
        except (ClientError, BotoCoreError, json.JSONDecodeError) as exc:
            logger.warning("S3 load failed for %s/%s: %s", self.bucket, self.key, exc)
            return {}

    def save(self, data: Dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        self._client().put_object(Bucket=self.bucket, Key=self.key, Body=body)


@dataclass
class ParameterStoreJSONStorage:
    name: str
    client: Any | None = None

    def _client(self):
        if self.client is None:
            import boto3  # type: ignore

            self.client = boto3.client("ssm")
        return self.client

    def load(self) -> Dict[str, Any]:
        try:
            resp = self._client().get_parameter(Name=self.name, WithDecryption=True)
            return json.loads(resp["Parameter"]["Value"])
        except (ClientError, BotoCoreError, json.JSONDecodeError) as exc:
            logger.warning("Parameter Store load failed for %s: %s", self.name, exc)
            return {}

    def save(self, data: Dict[str, Any]) -> None:
        self._client().put_parameter(
            Name=self.name,
            Value=json.dumps(data),
            Type="String",
            Overwrite=True,
        )


def get_storage(uri: str) -> JSONStorage:
    """Return a :class:`JSONStorage` for ``uri``.

    Parameters
    ----------
    uri:
        Storage location specified as ``file://``, ``s3://`` or ``ssm://``.
    """

    parsed = urlparse(uri)
    scheme = parsed.scheme or "file"

    if scheme == "s3":
        return S3JSONStorage(bucket=parsed.netloc, key=parsed.path.lstrip("/"))

    if scheme in {"ssm", "ssm-param", "parameter"}:
        name = parsed.netloc + parsed.path
        name = name.lstrip("/")
        return ParameterStoreJSONStorage(name=name)

    # default to file-based storage
    if scheme in {"file", ""}:
        path = parsed.path
        if parsed.netloc:
            path = os.path.join(parsed.netloc, path.lstrip("/"))
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        return FileJSONStorage(path=Path(path))

    raise ValueError(f"Unsupported storage scheme: {scheme}")


__all__ = [
    "JSONStorage",
    "FileJSONStorage",
    "S3JSONStorage",
    "ParameterStoreJSONStorage",
    "get_storage",
]
