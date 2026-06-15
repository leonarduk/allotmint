"""Deployed (AWS) writable-store behaviour for transactions routes (issue #4275)."""

from __future__ import annotations

import io
import json

import pytest
from fastapi import FastAPI, Request

from backend.common import data_loader
from backend.common.accounts_store import (
    WRITABLE_ACCOUNTS_PREFIX,
    S3AccountsStore,
)
from backend.routes import transactions as transactions_module


def _make_request(state: dict | None = None) -> Request:
    app = FastAPI()
    for key, value in (state or {}).items():
        setattr(app.state, key, value)
    scope = {
        "type": "http",
        "app": app,
        "method": "POST",
        "headers": [],
        "path": "/",
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    return Request(scope)


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def get_object(self, Bucket: str, Key: str):  # noqa: N803
        from botocore.exceptions import ClientError

        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_kwargs):  # noqa: N803
        self.objects[Key] = Body

    def list_objects_v2(self, Bucket: str, Prefix: str, **_kwargs):  # noqa: N803
        contents = [
            {"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}


def test_resolve_writable_store_uses_s3_in_aws(monkeypatch):
    monkeypatch.setattr(transactions_module.config, "app_env", "aws")
    monkeypatch.setenv(data_loader.DATA_BUCKET_ENV, "data-bucket")

    store = transactions_module.resolve_writable_store(_make_request())

    assert isinstance(store, S3AccountsStore)
    assert store.is_global is False
    assert store.bucket == "data-bucket"


def test_resolve_writable_store_falls_back_local_without_bucket(monkeypatch, tmp_path):
    monkeypatch.setattr(transactions_module.config, "app_env", "aws")
    monkeypatch.delenv(data_loader.DATA_BUCKET_ENV, raising=False)

    request = _make_request({"accounts_root": tmp_path})
    store = transactions_module.resolve_writable_store(request)

    assert not isinstance(store, S3AccountsStore)
    assert store.local_root == tmp_path.resolve()


@pytest.mark.asyncio
async def test_create_manual_holding_persists_to_s3(monkeypatch):
    monkeypatch.setattr(transactions_module.config, "app_env", "aws")
    monkeypatch.setenv(data_loader.DATA_BUCKET_ENV, "data-bucket")

    fake = _FakeS3()
    monkeypatch.setattr(
        transactions_module,
        "resolve_writable_store",
        lambda _req: S3AccountsStore(bucket="data-bucket", client=fake),
    )

    payload = transactions_module.ManualHoldingCreate(
        owner="alice", account="ISA", ticker="aaa", value_gbp=1000
    )
    result = await transactions_module.create_manual_holding(_make_request(), payload)

    assert result["status"] == "saved"
    key = f"{WRITABLE_ACCOUNTS_PREFIX}/alice/isa.json"
    assert key in fake.objects
    stored = json.loads(fake.objects[key].decode("utf-8"))
    assert stored["holdings"] == [{"ticker": "AAA", "value_gbp": 1000.0}]
    # The owner scaffold (person.json) is created in the writable prefix only.
    assert f"{WRITABLE_ACCOUNTS_PREFIX}/alice/person.json" in fake.objects
    assert not any(k.startswith("accounts/") for k in fake.objects)


@pytest.mark.asyncio
async def test_create_transaction_persists_to_s3(monkeypatch):
    monkeypatch.setattr(transactions_module.config, "app_env", "aws")
    monkeypatch.setenv(data_loader.DATA_BUCKET_ENV, "data-bucket")

    fake = _FakeS3()
    monkeypatch.setattr(
        transactions_module,
        "resolve_writable_store",
        lambda _req: S3AccountsStore(bucket="data-bucket", client=fake),
    )
    monkeypatch.setattr(
        transactions_module, "_rebuild_portfolio", lambda *a, **k: None
    )

    from datetime import date

    tx = transactions_module.TransactionCreate(
        owner="alice",
        account="ISA",
        ticker="AAA",
        date=date(2024, 1, 1),
        price_gbp=10.0,
        units=2.0,
        reason="diversify",
    )
    result = await transactions_module.create_transaction(_make_request(), tx)

    assert result["owner"] == "alice"
    key = f"{WRITABLE_ACCOUNTS_PREFIX}/alice/ISA_transactions.json"
    assert key in fake.objects
    stored = json.loads(fake.objects[key].decode("utf-8"))
    assert len(stored["transactions"]) == 1
    assert stored["transactions"][0]["ticker"] == "AAA"
