from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

DATA_BUCKET_ENV = "DATA_BUCKET"
PLOTS_PREFIX = "accounts/"

_METADATA_STEMS = {
    "person",
    "config",
    "notes",
    "settings",
    "approvals",
    "approval_requests",
    "pension-forecast",
    "pension_forecast",
}


class MissingData(FileNotFoundError):
    """Raised when requested data does not exist."""


class ProviderUnavailable(RuntimeError):
    """Raised when a backing provider cannot be reached or initialized."""


class InvalidPayload(ValueError):
    """Raised when provider data exists but cannot be parsed or is empty."""


@dataclass(frozen=True)
class AccountObject:
    owner: str
    account: str
    data: Dict[str, Any]


@dataclass(frozen=True)
class OwnerMetadata:
    owner: str
    metadata: Dict[str, Any]


class LocalDataProvider:
    def load_account(self, owner: str, account: str, root: Path) -> AccountObject:
        path = root / owner / f"{account}.json"
        try:
            data = _safe_json_load(path)
        except json.JSONDecodeError as exc:
            raise InvalidPayload(f"Invalid JSON file: {path}") from exc
        return AccountObject(owner=owner, account=account, data=data)

    def load_person_meta(self, owner: str, root: Path) -> OwnerMetadata:
        path = root / owner / "person.json"
        if not path.exists():
            raise MissingData(str(path))
        try:
            data = _safe_json_load(path)
        except json.JSONDecodeError as exc:
            raise InvalidPayload(f"Invalid JSON file: {path}") from exc
        return OwnerMetadata(owner=owner, metadata=_extract_person_meta(data))

    def list_plots(self, current_user: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError("Local plot discovery remains in data_loader")


class S3DataProvider:
    def __init__(self, bucket: Optional[str] = None) -> None:
        self.bucket = bucket or os.getenv(DATA_BUCKET_ENV)
        if not self.bucket:
            raise ProviderUnavailable(f"Missing {DATA_BUCKET_ENV} env var for AWS account loading")

    def _client(self):
        try:
            import boto3  # type: ignore
        except Exception as exc:  # pragma: no cover - import failure is environment-specific
            raise ProviderUnavailable("boto3 is not available") from exc
        try:
            return boto3.client("s3")
        except Exception as exc:  # pragma: no cover - client creation is environment-specific
            raise ProviderUnavailable("Unable to create S3 client") from exc

    def load_account(self, owner: str, account: str) -> AccountObject:
        key = f"{PLOTS_PREFIX}{owner}/{account}.json"
        obj = self._get_object(key)
        return AccountObject(owner=owner, account=account, data=_parse_json_body(obj.get("Body"), f"s3://{self.bucket}/{key}"))

    def load_person_meta(self, owner: str) -> OwnerMetadata:
        key = f"{PLOTS_PREFIX}{owner}/person.json"
        obj = self._get_object(key)
        data = _parse_json_body(obj.get("Body"), f"s3://{self.bucket}/{key}")
        return OwnerMetadata(owner=owner, metadata=_extract_person_meta(data))

    def list_plots(self, current_user: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._client()
        owners: Dict[str, List[str]] = {}
        token: str | None = None

        while True:
            params = {"Bucket": self.bucket, "Prefix": PLOTS_PREFIX}
            if token:
                params["ContinuationToken"] = token
            try:
                resp = client.list_objects_v2(**params)
            except Exception as exc:
                raise ProviderUnavailable(f"Unable to list objects in s3://{self.bucket}/{PLOTS_PREFIX}") from exc
            for item in resp.get("Contents", []):
                key = item.get("Key", "")
                if not key.lower().endswith(".json") or not key.startswith(PLOTS_PREFIX):
                    continue
                rel = key[len(PLOTS_PREFIX) :]
                parts = rel.split("/")
                if len(parts) != 2:
                    continue
                owner, filename = parts
                stem = Path(filename).stem
                if stem.lower() in _METADATA_STEMS:
                    continue
                accounts = owners.setdefault(owner, [])
                if all(existing.lower() != stem.lower() for existing in accounts):
                    accounts.append(stem)
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break

        return [{"owner": owner, "accounts": accounts} for owner, accounts in sorted(owners.items())]

    def _get_object(self, key: str) -> Dict[str, Any]:
        client = self._client()
        try:
            return client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise MissingData(f"s3://{self.bucket}/{key}") from exc
            raise ProviderUnavailable(f"Unable to load s3://{self.bucket}/{key}") from exc
        except BotoCoreError as exc:
            raise ProviderUnavailable(f"Unable to load s3://{self.bucket}/{key}") from exc
        except Exception as exc:
            raise ProviderUnavailable(f"Unable to load s3://{self.bucket}/{key}") from exc


def _safe_json_load(path: Path) -> Dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        raise MissingData(str(path))
    with open(path, "r", encoding="utf-8-sig") as handle:
        txt = handle.read().strip()
    if not txt:
        raise InvalidPayload(f"Empty JSON file: {path}")
    return json.loads(txt)


def _parse_json_body(body: Any, source: str) -> Dict[str, Any]:
    txt = body.read().decode("utf-8-sig").strip() if body else ""
    if not txt:
        raise InvalidPayload(f"Empty JSON file: {source}")
    try:
        return json.loads(txt)
    except json.JSONDecodeError as exc:
        raise InvalidPayload(f"Invalid JSON file: {source}") from exc


def _extract_person_meta(data: Dict[str, Any]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    allowed_keys = {
        "owner",
        "full_name",
        "display_name",
        "preferred_name",
        "dob",
        "email",
        "holdings",
        "viewers",
    }
    for key in allowed_keys:
        if key in data:
            meta[key] = data[key]
    if "viewers" not in meta:
        meta["viewers"] = data.get("viewers", [])
    return meta
