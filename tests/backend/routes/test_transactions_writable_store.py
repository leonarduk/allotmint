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

    store, _ = transactions_module.resolve_writable_store(_make_request())

    assert isinstance(store, S3AccountsStore)
    assert store.is_global is False
    assert store.bucket == "data-bucket"


def test_resolve_writable_store_falls_back_local_without_bucket(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(transactions_module.config, "app_env", "aws")
    monkeypatch.delenv(data_loader.DATA_BUCKET_ENV, raising=False)
    monkeypatch.setattr(transactions_module, "_warned_missing_data_bucket", False)

    request = _make_request({"accounts_root": tmp_path})
    with caplog.at_level("WARNING", logger="transactions"):
        store, _ = transactions_module.resolve_writable_store(request)

    assert not isinstance(store, S3AccountsStore)
    assert store.local_root == tmp_path.resolve()
    assert any(
        data_loader.DATA_BUCKET_ENV in record.message for record in caplog.records
    )


def test_resolve_writable_store_no_warning_outside_aws(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(transactions_module.config, "app_env", "local")
    monkeypatch.delenv(data_loader.DATA_BUCKET_ENV, raising=False)

    request = _make_request({"accounts_root": tmp_path})
    with caplog.at_level("WARNING", logger="transactions"):
        transactions_module.resolve_writable_store(request)

    assert not any(
        data_loader.DATA_BUCKET_ENV in record.message for record in caplog.records
    )


def test_resolve_writable_store_warns_only_once_per_process(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(transactions_module.config, "app_env", "aws")
    monkeypatch.delenv(data_loader.DATA_BUCKET_ENV, raising=False)
    monkeypatch.setattr(transactions_module, "_warned_missing_data_bucket", False)

    with caplog.at_level("WARNING", logger="transactions"):
        for _ in range(3):
            transactions_module.resolve_writable_store(
                _make_request({"accounts_root": tmp_path})
            )

    warnings = [
        record
        for record in caplog.records
        if data_loader.DATA_BUCKET_ENV in record.message
    ]
    assert len(warnings) == 1


@pytest.mark.asyncio
async def test_create_manual_holding_persists_to_s3(monkeypatch):
    monkeypatch.setattr(transactions_module.config, "app_env", "aws")
    monkeypatch.setenv(data_loader.DATA_BUCKET_ENV, "data-bucket")

    fake = _FakeS3()
    monkeypatch.setattr(
        transactions_module,
        "resolve_writable_store",
        lambda _req: (S3AccountsStore(bucket="data-bucket", client=fake), transactions_module._RootResolution.WRITABLE),
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
        lambda _req: (S3AccountsStore(bucket="data-bucket", client=fake), transactions_module._RootResolution.WRITABLE),
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


class TestReadEndpointsWithNonexistentRoot:
    """A configured accounts_root that doesn't exist on disk must not crash read
    endpoints (issue #4449). Write endpoints already return a clear 400 via
    _require_writable_store's is_global check; these read endpoints instead
    call resolve_writable_store directly and must degrade to "no data" rather
    than raising when the resolved local_root path is missing."""

    @staticmethod
    def _nonexistent_request(tmp_path):
        return _make_request({"accounts_root": tmp_path / "does-not-exist"})

    @pytest.mark.asyncio
    async def test_list_transactions_returns_empty_list(self, tmp_path):
        result = await transactions_module.list_transactions(self._nonexistent_request(tmp_path))
        assert result == []

    @pytest.mark.asyncio
    async def test_list_manual_holdings_returns_empty_accounts(self, tmp_path):
        # A owner absent from both the (nonexistent) writable root and the
        # global demo dataset -- unlike list_transactions/
        # transactions_with_compliance, this endpoint also merges in the
        # global demo dataset, so a real demo owner like "alice" would
        # legitimately return non-empty data here.
        result = await transactions_module.list_manual_holdings(
            self._nonexistent_request(tmp_path), owner="no-such-demo-owner"
        )
        assert result == {"owner": "no-such-demo-owner", "accounts": []}

    @pytest.mark.asyncio
    async def test_transactions_with_compliance_returns_empty_list(self, tmp_path):
        result = await transactions_module.transactions_with_compliance("alice", self._nonexistent_request(tmp_path))
        assert result == {"transactions": []}
