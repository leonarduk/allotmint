import io
import json
import sys
import types
from datetime import date

import pytest

import backend.reports as reports


def test_load_transactions_handles_malformed_json(tmp_path, monkeypatch, caplog):
    owner = "alice"
    owner_dir = tmp_path / owner
    owner_dir.mkdir()

    good = owner_dir / "good_transactions.json"
    good.write_text(json.dumps({"transactions": [{"id": 1}]}))

    bad = owner_dir / "bad_transactions.json"
    bad.write_text("{not json")

    monkeypatch.setattr(reports, "_transaction_roots", lambda: [str(tmp_path)])
    monkeypatch.setattr(reports.config, "app_env", "local")

    with caplog.at_level("WARNING"):
        records = reports._load_transactions(owner)

    assert records == [{"id": 1}]
    assert "failed to read" in caplog.text


def test_load_transactions_s3(monkeypatch, caplog):
    owner = "alice"
    monkeypatch.setattr(reports.config, "app_env", "aws")
    monkeypatch.setenv("DATA_BUCKET", "bucket")

    class FakeBotoCoreError(Exception):
        pass

    class FakeClientError(Exception):
        pass

    exceptions_mod = types.ModuleType("exceptions")
    exceptions_mod.BotoCoreError = FakeBotoCoreError
    exceptions_mod.ClientError = FakeClientError
    botocore_mod = types.ModuleType("botocore")
    botocore_mod.exceptions = exceptions_mod
    monkeypatch.setitem(sys.modules, "botocore", botocore_mod)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", exceptions_mod)

    class FakePaginator:
        def paginate(self, Bucket, Prefix):
            return [
                {
                    "Contents": [
                        {"Key": f"transactions/{owner}/good_transactions.json"},
                        {"Key": f"transactions/{owner}/error_transactions.json"},
                        {"Key": f"transactions/{owner}/ignore.txt"},
                    ]
                }
            ]

    class FakeS3Client:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator()

        def get_object(self, Bucket, Key):
            if Key.endswith("error_transactions.json"):
                raise FakeBotoCoreError("boom")
            data = b'{"transactions": [{"id": 1}]}'
            return {"Body": io.BytesIO(data)}

    boto3_mod = types.ModuleType("boto3")
    boto3_mod.client = lambda name: FakeS3Client()
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)

    with caplog.at_level("WARNING"):
        records = reports._load_transactions(owner)

    assert records == [{"id": 1}]
    assert "failed to load" in caplog.text


def test_compile_report_filters_and_totals(monkeypatch):
    txs = [
        {"date": "2024-01-01", "type": "SELL", "amount_minor": 1000},
        {"date": "2024-01-02", "type": "SELL", "amount_minor": 2000},
        {"date": "2024-01-03", "type": "DIVIDEND", "amount_minor": 500},
        {"date": "2024-01-04", "type": "INTEREST", "amount_minor": 300},
    ]

    monkeypatch.setattr(reports, "_load_transactions", lambda owner: txs)
    performance = {
        "history": [
            {"date": "2024-01-01", "cumulative_return": 0.1},
            {"date": "2024-01-02", "cumulative_return": 0.2},
            {"date": "2024-01-03", "cumulative_return": 0.3},
            {"date": "2024-01-04", "cumulative_return": 0.4},
        ],
        "max_drawdown": -0.1,
    }
    monkeypatch.setattr("backend.common.portfolio_utils.compute_owner_performance", lambda owner: performance)

    start = date(2024, 1, 2)
    end = date(2024, 1, 3)
    data = reports.compile_report("alice", start=start, end=end)

    assert data.realized_gains_gbp == 20.0
    assert data.income_gbp == 5.0
    assert data.cumulative_return == 0.3
    assert data.max_drawdown == -0.1


def test_load_transactions_requires_data_bucket(monkeypatch):
    monkeypatch.setattr(reports.config, "app_env", "aws")
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    with pytest.raises(RuntimeError, match="DATA_BUCKET environment variable is required in AWS"):
        reports._load_transactions("alice")
