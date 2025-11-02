import io
import json
import sys
import types
from datetime import date

import json
from datetime import date, datetime
from types import SimpleNamespace

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


def test_load_transactions_skips_missing_owner_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(reports.config, "app_env", "local", raising=False)
    monkeypatch.setattr(reports, "_transaction_roots", lambda: [tmp_path.as_posix()])

    assert reports._load_transactions("alice") == []


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
    reports.get_template_store.cache_clear()
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


def test_get_template_returns_user_definition(tmp_path, monkeypatch):
    original_get_store = reports.get_template_store
    original_get_store.cache_clear()
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
                "columns": [{"key": "metric", "label": "Metric", "type": "string"}],
            }
        ],
    }
    store.create_template(definition)
    monkeypatch.setattr(reports, "get_template_store", lambda: store)

    template = reports.get_template("custom")

    assert template is not None
    assert template.template_id == "custom"
    original_get_store.cache_clear()


def test_get_template_returns_none_for_missing(monkeypatch):
    original_get_store = reports.get_template_store
    original_get_store.cache_clear()
    monkeypatch.setattr(
        reports,
        "get_template_store",
        lambda: SimpleNamespace(get_template=lambda template_id: None),
    )

    assert reports.get_template("missing") is None

    original_get_store.cache_clear()


def test_file_template_store_filters_invalid_definitions(tmp_path, caplog):
    store = reports.FileTemplateStore(tmp_path)
    valid = {
        "template_id": "valid",
        "name": "Valid",
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
    store.create_template(valid)

    # Corrupt JSON file should be skipped with a warning
    (tmp_path / "broken.json").write_text("{not json")

    # Invalid schema (missing name) should also be skipped
    (tmp_path / "invalid.json").write_text(
        json.dumps({
            "template_id": "invalid",
            "sections": [],
        })
    )

    with caplog.at_level("WARNING", logger=reports.logger.name):
        templates = store.list_templates()

    assert [t["template_id"] for t in templates] == ["valid"]
    assert "failed to load report template" in caplog.text
    assert "invalid template definition" in caplog.text


def test_file_template_store_get_template_handles_invalid_json(tmp_path, caplog):
    store = reports.FileTemplateStore(tmp_path)
    (tmp_path / "example.json").write_text("{not json")

    with caplog.at_level("WARNING", logger=reports.logger.name):
        template = store.get_template("example")

    assert template is None
    assert "failed to load report template" in caplog.text


def test_get_template_store_requires_aws_configuration(monkeypatch):
    reports.get_template_store.cache_clear()
    monkeypatch.setattr(reports.config, "app_env", "aws", raising=False)
    monkeypatch.delenv("REPORT_TEMPLATES_TABLE", raising=False)

    with pytest.raises(RuntimeError, match="REPORT_TEMPLATES_TABLE"):
        reports.get_template_store()


def test_get_template_store_local_returns_file_store(monkeypatch, tmp_path):
    reports.get_template_store.cache_clear()
    monkeypatch.setattr(reports.config, "app_env", "local", raising=False)
    monkeypatch.setattr(reports.config, "data_root", tmp_path, raising=False)

    store = reports.get_template_store()

    assert isinstance(store, reports.FileTemplateStore)
    assert store.root == tmp_path / "reports"


def test_report_context_transactions_filters_and_sorts(monkeypatch):
    raw = [
        {"date": "2024-01-02", "type": "sell", "amount_minor": 200},
        {"date": "invalid", "type": "buy", "amount_minor": 100},
        {"date": "2024-01-01", "type": "buy", "amount_minor": 100},
    ]

    monkeypatch.setattr(reports, "_load_transactions", lambda owner: raw)
    monkeypatch.setattr(
        reports, "_compile_summary", lambda owner, start, end: (
            reports.ReportData(
                owner=owner,
                start=None,
                end=None,
                realized_gains_gbp=0.0,
                income_gbp=0.0,
                cumulative_return=None,
                max_drawdown=None,
            ),
            {},
        )
    )

    context = reports.ReportContext("alice", start=date(2024, 1, 1), end=None)
    rows = context.transactions()

    assert [row["date"] for row in rows] == ["2024-01-01", "2024-01-02", "invalid"]


def test_report_context_allocation_handles_errors(monkeypatch):
    summary = reports.ReportData(
        owner="alice",
        start=None,
        end=None,
        realized_gains_gbp=0.0,
        income_gbp=0.0,
        cumulative_return=None,
        max_drawdown=None,
    )
    monkeypatch.setattr(reports, "_compile_summary", lambda owner, start, end: (summary, {}))
    monkeypatch.setattr(
        reports.portfolio_utils,
        "portfolio_value_breakdown",
        lambda owner, date: (_ for _ in ()).throw(FileNotFoundError()),
    )

    context = reports.ReportContext("alice", start=None, end=None)
    assert context.allocation() == []


def test_report_context_allocation_rounds_and_sorts(monkeypatch):
    summary = reports.ReportData(
        owner="alice",
        start=None,
        end=date(2024, 1, 1),
        realized_gains_gbp=0.0,
        income_gbp=0.0,
        cumulative_return=None,
        max_drawdown=None,
    )
    perf = {"reporting_date": "2024-01-01"}

    monkeypatch.setattr(reports, "_compile_summary", lambda owner, start, end: (summary, perf))

    rows = [
        {"ticker": "XYZ.L", "exchange": "L", "units": 1.23456, "price": 9.8765, "value": 123.4567},
        {"ticker": "ABC.N", "exchange": "N", "units": None, "price": None, "value": None},
    ]

    def fake_breakdown(owner, date):
        assert date == "2024-01-01"
        return rows

    monkeypatch.setattr(reports.portfolio_utils, "portfolio_value_breakdown", fake_breakdown)

    context = reports.ReportContext("alice", start=None, end=date(2024, 1, 1))
    allocation = context.allocation()

    assert allocation[0] == {
        "ticker": "XYZ.L",
        "exchange": "L",
        "units": 1.2346,
        "price": 9.8765,
        "value": 123.46,
    }
    assert allocation[1]["ticker"] == "ABC.N"


def test_build_report_document_warns_on_missing_builder(monkeypatch, caplog):
    template = reports.ReportTemplate(
        template_id="custom",
        name="Custom",
        description="",
        sections=(
            reports.ReportSectionSchema(
                id="mystery",
                title="Mystery",
                source="unknown.section",
                columns=(),
            ),
        ),
        builtin=False,
    )

    monkeypatch.setattr(reports, "get_template", lambda template_id, store=None: template)
    monkeypatch.setattr(
        reports, "ReportContext", lambda owner, start=None, end=None: SimpleNamespace(
            summary=lambda: reports.ReportData(
                owner=owner,
                start=None,
                end=None,
                realized_gains_gbp=0.0,
                income_gbp=0.0,
                cumulative_return=None,
                max_drawdown=None,
            ),
        )
    )

    with caplog.at_level("WARNING", logger=reports.logger.name):
        document = reports.build_report_document("custom", "alice")

    assert document.sections[0].rows == ()
    assert "No builder registered" in caplog.text


def test_section_to_dataframe_includes_missing_columns():
    schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        columns=(
            reports.ReportColumnSchema("metric", "Metric"),
            reports.ReportColumnSchema("value", "Value"),
            reports.ReportColumnSchema("units", "Units"),
        ),
    )
    section = reports.ReportSectionData(
        schema=schema,
        rows=({"metric": "Owner", "value": "alice"},),
    )

    df = reports._section_to_dataframe(section)

    assert list(df.columns) == ["Metric", "Value", "Units"]
    assert df.iloc[0].to_dict() == {"Metric": "Owner", "Value": "alice", "Units": None}


def test_section_to_dataframe_empty_creates_headers():
    schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        columns=(
            reports.ReportColumnSchema("metric", "Metric"),
            reports.ReportColumnSchema("value", "Value"),
        ),
    )
    section = reports.ReportSectionData(schema=schema, rows=())

    df = reports._section_to_dataframe(section)

    assert df.empty
    assert list(df.columns) == ["Metric", "Value"]


def test_report_to_csv_includes_metadata(tmp_path):
    schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        columns=(
            reports.ReportColumnSchema("metric", "Metric"),
            reports.ReportColumnSchema("value", "Value"),
        ),
    )
    template = reports.ReportTemplate(
        template_id="example",
        name="Example",
        description="",
        sections=(schema,),
        builtin=True,
    )
    section = reports.ReportSectionData(
        schema=schema,
        rows=(
            {"metric": "Owner", "value": "alice"},
            {"metric": "Transactions", "value": 2},
        ),
    )
    document = reports.ReportDocument(
        template=template,
        owner="alice",
        generated_at=datetime.now(tz=reports.UTC),
        parameters={"start": "2024-01-01"},
        sections=(section,),
    )

    csv_bytes = reports.report_to_csv(document)
    content = csv_bytes.decode("utf-8")

    assert "Template: Example" in content
    assert "start: 2024-01-01" in content
    assert "Metric,Value" in content


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-01-01", date(2024, 1, 1)),
        ("invalid", None),
        (None, None),
    ],
)
def test_parse_date_handles_invalid_values(value, expected):
    assert reports._parse_date(value) == expected


def test_transaction_roots_local(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    transactions_dir = data_root / "transactions"
    transactions_dir.mkdir()

    output_root = tmp_path / "output"
    output_root.mkdir()
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()

    monkeypatch.setattr(reports.config, "app_env", "local", raising=False)
    monkeypatch.setattr(reports.config, "transactions_output_root", output_root, raising=False)
    monkeypatch.setattr(reports.config, "accounts_root", accounts_root, raising=False)
    monkeypatch.setattr(reports.config, "data_root", data_root, raising=False)

    roots = list(reports._transaction_roots())

    assert output_root.as_posix() in roots
    assert accounts_root.as_posix() in roots
    assert transactions_dir.as_posix() in roots
