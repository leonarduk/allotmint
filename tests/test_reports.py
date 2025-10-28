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
    monkeypatch.setattr(
        "backend.common.portfolio_utils.compute_owner_performance",
        lambda owner, **kwargs: performance,
    )

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


def test_build_report_document_uses_context(monkeypatch):
    history = [
        {"date": "2024-01-01", "value": 100.0, "daily_return": 0.1, "weekly_return": 0.2, "cumulative_return": 0.3, "drawdown": 0.0},
    ]
    summary = reports.ReportData(
        owner="alice",
        start=None,
        end=None,
        realized_gains_gbp=15.0,
        income_gbp=5.0,
        cumulative_return=0.3,
        max_drawdown=-0.1,
        history=history,
    )
    performance = {"history": history, "reporting_date": "2024-01-01", "max_drawdown": -0.1}

    monkeypatch.setattr(reports, "_compile_summary", lambda owner, start, end: (summary, performance))
    monkeypatch.setattr(reports, "_load_transactions", lambda owner: [
        {"date": "2024-01-01", "type": "SELL", "amount_minor": 1000, "currency": "GBP"}
    ])
    monkeypatch.setattr(
        reports.portfolio_utils,
        "portfolio_value_breakdown",
        lambda owner, date: [
            {"ticker": "ABC", "exchange": "L", "units": 2, "price": 10.5, "value": 21.0}
        ],
    )

    document = reports.build_report_document("performance-summary", "alice")
    assert document.template.template_id == "performance-summary"
    metrics = {row["metric"]: row["value"] for row in document.sections[0].rows}
    assert metrics["Realized gains"] == 15.0
    assert metrics["Transactions"] == 1
    history_rows = document.sections[1].rows
    assert history_rows[0]["date"] == "2024-01-01"


def test_list_template_metadata_merges_user_templates(tmp_path):
    store = reports.FileTemplateStore(tmp_path)
    definition = {
        "template_id": "custom",
        "name": "Custom",
        "description": "",
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "source": "performance.metrics",
                "columns": [
                    {"key": "metric", "label": "Metric", "type": "string"},
                ],
            }
        ],
    }
    store.create_template(definition)

    templates = reports.list_template_metadata(store=store)
    ids = {t["template_id"] for t in templates}
    assert "performance-summary" in ids
    assert "custom" in ids


def test_create_update_delete_user_template(tmp_path):
    store = reports.FileTemplateStore(tmp_path)
    definition = {
        "template_id": "custom",
        "name": "Custom",
        "description": "",
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "source": "performance.metrics",
                "columns": [
                    {"key": "metric", "label": "Metric", "type": "string"},
                ],
            }
        ],
    }

    template = reports.create_user_template(definition, store=store)
    assert template.template_id == "custom"

    updated = reports.update_user_template(
        "custom",
        {
            "name": "Custom v2",
            "description": "",
            "sections": definition["sections"],
        },
        store=store,
    )
    assert updated.name == "Custom v2"

    reports.delete_user_template("custom", store=store)
    assert store.get_template("custom") is None
