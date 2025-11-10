import json
import sys
from datetime import UTC, date, datetime
from types import SimpleNamespace
import pytest

import backend.reports as reports


def test_report_dataclasses_to_dict():
    section_schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        columns=(reports.ReportColumnSchema("metric", "Metric"),),
    )
    section = reports.ReportSectionData(schema=section_schema, rows=({"metric": "Owner"},))
    document = reports.ReportDocument(
        template=reports.PERFORMANCE_SUMMARY_TEMPLATE,
        owner="alice",
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
        parameters={"start": "2024-01-01"},
        sections=(section,),
    )
    payload = document.to_dict()

    assert payload["owner"] == "alice"
    assert payload["sections"][0]["rows"] == [{"metric": "Owner"}]

    data = reports.ReportData(
        owner="alice",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        realized_gains_gbp=10.123,
        income_gbp=5.678,
        cumulative_return=0.1234,
        max_drawdown=-0.25,
        history=[{"date": "2024-01-01"}],
    )
    summary = data.to_dict()

    assert summary["realized_gains_gbp"] == 10.12
    assert summary["history"] == [{"date": "2024-01-01"}]


def test_template_store_methods_raise_not_implemented():
    store = reports.TemplateStore()
    with pytest.raises(NotImplementedError):
        store.list_templates()
    with pytest.raises(NotImplementedError):
        store.get_template("example")
    with pytest.raises(NotImplementedError):
        store.create_template({})
    with pytest.raises(NotImplementedError):
        store.update_template({})
    with pytest.raises(NotImplementedError):
        store.delete_template("example")


def test_file_template_store_error_paths(tmp_path, caplog):
    store = reports.FileTemplateStore(tmp_path)
    definition = {
        "template_id": "example",
        "name": "Example",
        "description": "",
        "sections": [
            {
                "id": "metrics",
                "title": "Metrics",
                "source": "performance.metrics",
                "columns": [{"key": "metric", "label": "Metric"}],
            }
        ],
    }
    store.create_template(definition)

    with pytest.raises(FileExistsError):
        store.create_template(definition)

    missing = store.root / "missing.json"
    missing.write_text(json.dumps({"template_id": "missing", "sections": []}))
    with caplog.at_level("WARNING", logger=reports.logger.name):
        assert store.get_template("missing") is None
    assert "invalid template definition" in caplog.text

    with pytest.raises(FileNotFoundError):
        store.update_template({"template_id": "absent"})

    with pytest.raises(FileNotFoundError):
        store.delete_template("absent")


def _install_fake_boto_modules(monkeypatch, table):
    exceptions_mod = SimpleNamespace(ClientError=type("ClientError", (Exception,), {}))
    boto3_mod = SimpleNamespace(
        resource=lambda name: SimpleNamespace(Table=lambda table_name: table),
    )
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
    monkeypatch.setitem(sys.modules, "botocore", SimpleNamespace(exceptions=exceptions_mod))
    monkeypatch.setitem(sys.modules, "botocore.exceptions", exceptions_mod)


def test_dynamo_template_store_list_and_get(monkeypatch, caplog):
    class FakeTable:
        def __init__(self):
            self.scan_calls: list[dict[str, object]] = []
            self.put_requests: list[dict[str, object]] = []
            self.delete_requests: list[dict[str, object]] = []

        def scan(self, **params):
            self.scan_calls.append(params)
            if not params:
                return {
                    "Items": [
                        {"definition": json.dumps({"template_id": "custom", "name": "Custom", "description": "", "sections": [
                            {
                                "id": "metrics",
                                "title": "Metrics",
                                "source": "performance.metrics",
                                "columns": [{"key": "metric", "label": "Metric"}],
                            }
                        ]})},
                        {"definition": "not json"},
                        {"definition": json.dumps({"template_id": "invalid", "name": "", "sections": []})},
                    ],
                    "LastEvaluatedKey": {"token": "1"},
                }
            return {
                "Items": [
                    {"definition": json.dumps({"template_id": "other", "name": "Other", "description": "", "sections": [
                        {
                            "id": "metrics",
                            "title": "Metrics",
                            "source": "performance.metrics",
                            "columns": [{"key": "metric", "label": "Metric"}],
                        }
                    ]})}
                ]
            }

        def get_item(self, Key):
            if Key["template_id"] == "missing":
                return {}
            if Key["template_id"] == "invalid":
                return {"Item": {"definition": "not json"}}
            if Key["template_id"] == "baddef":
                return {"Item": {"definition": json.dumps({"template_id": "baddef", "name": "", "sections": []})}}
            return {
                "Item": {
                    "definition": json.dumps({
                        "template_id": Key["template_id"],
                        "name": "Loaded",
                        "description": "",
                        "sections": [
                            {
                                "id": "metrics",
                                "title": "Metrics",
                                "source": "performance.metrics",
                                "columns": [{"key": "metric", "label": "Metric"}],
                            }
                        ],
                    })
                }
            }

        def put_item(self, **kwargs):
            self.put_requests.append(kwargs)

        def delete_item(self, **kwargs):
            self.delete_requests.append(kwargs)

    table = FakeTable()
    _install_fake_boto_modules(monkeypatch, table)

    store = reports.DynamoTemplateStore("reports-table")

    with caplog.at_level("WARNING", logger=reports.logger.name):
        templates = store.list_templates()

    assert sorted(t["template_id"] for t in templates) == ["custom", "other"]
    assert "Invalid JSON" in caplog.text
    assert "invalid template definition in Dynamo" in caplog.text

    assert store.get_template("missing") is None
    assert store.get_template("invalid") is None
    assert store.get_template("baddef") is None

    template = store.get_template("custom")
    assert template["template_id"] == "custom"

    store.create_template(template)
    store.update_template(template)
    store.delete_template("custom")

    assert table.put_requests[0]["ConditionExpression"] == "attribute_not_exists(template_id)"
    assert table.put_requests[1]["ConditionExpression"] == "attribute_exists(template_id)"
    assert table.delete_requests[0]["ConditionExpression"] == "attribute_exists(template_id)"


def test_list_templates_handles_conflicts(monkeypatch, caplog):
    class FakeStore(reports.TemplateStore):
        def list_templates(self):
            return [
                {
                    "template_id": "performance-summary",
                    "name": "Duplicate",
                    "description": "",
                    "sections": [
                        {
                            "id": "metrics",
                            "title": "Metrics",
                            "source": "performance.metrics",
                            "columns": [{"key": "metric", "label": "Metric"}],
                        }
                    ],
                }
            ]

    store = FakeStore()
    monkeypatch.setattr(reports, "get_template_store", lambda: store)

    with caplog.at_level("WARNING", logger=reports.logger.name):
        templates = reports.list_templates()

    assert any(t.template_id == "performance-summary" for t in templates)
    assert "clashes with a built-in" in caplog.text


def test_list_templates_handles_store_errors(monkeypatch, caplog):
    class FailingStore(reports.TemplateStore):
        def list_templates(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(reports, "get_template_store", lambda: FailingStore())

    with caplog.at_level("WARNING", logger=reports.logger.name):
        reports.list_templates()

    assert "Failed to list user templates" in caplog.text


def test_user_template_management_errors(monkeypatch):
    store = SimpleNamespace(
        get_template=lambda template_id: None,
        create_template=lambda payload: None,
        update_template=lambda payload: None,
        delete_template=lambda template_id: None,
    )
    monkeypatch.setattr(reports, "get_template_store", lambda: store)

    with pytest.raises(ValueError):
        reports.create_user_template({"template_id": reports.DEFAULT_TEMPLATE_ID, "name": "Built-in", "sections": [
            {"id": "metrics", "title": "Metrics", "source": "performance.metrics", "columns": [{"key": "metric"}]}
        ]})

    store.get_template = lambda template_id: {"template_id": template_id}
    with pytest.raises(ValueError):
        reports.create_user_template({"template_id": "custom", "name": "Custom", "sections": [
            {"id": "metrics", "title": "Metrics", "source": "performance.metrics", "columns": [{"key": "metric"}]}
        ]})

    store.get_template = lambda template_id: None
    with pytest.raises(ValueError):
        reports.update_user_template(reports.DEFAULT_TEMPLATE_ID, {"name": "Built-in", "sections": [
            {"id": "metrics", "title": "Metrics", "source": "performance.metrics", "columns": [{"key": "metric"}]}
        ]})

    with pytest.raises(FileNotFoundError):
        reports.update_user_template("missing", {"name": "Custom", "sections": [
            {"id": "metrics", "title": "Metrics", "source": "performance.metrics", "columns": [{"key": "metric"}]}
        ]})

    store.get_template = lambda template_id: None
    with pytest.raises(ValueError):
        reports.delete_user_template(reports.DEFAULT_TEMPLATE_ID)

    with pytest.raises(FileNotFoundError):
        reports.delete_user_template("missing")


def test_build_report_document_requires_known_template(monkeypatch):
    monkeypatch.setattr(reports, "get_template", lambda template_id, store=None: None)

    with pytest.raises(ValueError):
        reports.build_report_document("unknown", "alice")


def test_transaction_roots_aws(monkeypatch):
    monkeypatch.setattr(reports.config, "app_env", "aws", raising=False)
    assert list(reports._transaction_roots()) == ["transactions"]


def test_load_transactions_s3_pagination_errors(monkeypatch, caplog):
    monkeypatch.setattr(reports.config, "app_env", "aws", raising=False)
    monkeypatch.setenv("DATA_BUCKET", "bucket")

    class FakeBotoCoreError(Exception):
        pass

    class FakeClientError(Exception):
        pass

    class FakePaginator:
        def paginate(self, **kwargs):
            raise FakeBotoCoreError()

    class FakeS3:
        def get_paginator(self, name):
            return FakePaginator()

    def fake_client(name):
        return FakeS3()

    boto3_mod = SimpleNamespace(client=fake_client)
    exceptions_mod = SimpleNamespace(BotoCoreError=FakeBotoCoreError, ClientError=FakeClientError)
    monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
    monkeypatch.setitem(sys.modules, "botocore", SimpleNamespace(exceptions=exceptions_mod))
    monkeypatch.setitem(sys.modules, "botocore.exceptions", exceptions_mod)

    with caplog.at_level("WARNING", logger=reports.logger.name):
        assert reports._load_transactions("alice") == []

    assert "failed to paginate S3 objects" in caplog.text


def test_get_template_store_returns_dynamo(monkeypatch):
    class EmptyTable:
        def scan(self, **kwargs):
            return {}

        def get_item(self, **kwargs):
            return {}

        def put_item(self, **kwargs):
            return {}

        def delete_item(self, **kwargs):
            return {}

    reports.get_template_store.cache_clear()
    monkeypatch.setattr(reports.config, "app_env", "aws", raising=False)
    monkeypatch.setenv("REPORT_TEMPLATES_TABLE", "reports-table")
    _install_fake_boto_modules(monkeypatch, EmptyTable())

    store = reports.get_template_store()

    assert isinstance(store, reports.DynamoTemplateStore)

    reports.get_template_store.cache_clear()


def test_compile_summary_filters_history(monkeypatch):
    monkeypatch.setattr(reports, "_load_transactions", lambda owner: [
        {"date": "2024-01-01", "type": "SELL", "amount_minor": 1000},
        {"date": "invalid", "type": "DIVIDEND", "amount_minor": 200},
    ])

    performance = {
        "history": [
            {"date": "2024-01-01", "cumulative_return": 0.1},
            {"date": "2024-01-05", "cumulative_return": 0.2},
            {"date": "invalid"},
        ],
        "max_drawdown": -0.2,
    }
    monkeypatch.setattr(reports.portfolio_utils, "compute_owner_performance", lambda owner: performance)

    summary, perf = reports._compile_summary("alice", start=date(2024, 1, 2), end=date(2024, 1, 6))

    assert summary.realized_gains_gbp == 0.0
    assert summary.income_gbp == 2.0
    assert summary.history == [{"date": "2024-01-05", "cumulative_return": 0.2}]
    assert perf is performance


def test_report_to_csv_multiple_sections():
    schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        columns=(reports.ReportColumnSchema("metric", "Metric"),),
    )
    section = reports.ReportSectionData(schema=schema, rows=({"metric": "Owner"},))
    template = reports.ReportTemplate(
        template_id="example",
        name="Example",
        description="",
        sections=(schema, schema),
        builtin=False,
    )
    document = reports.ReportDocument(
        template=template,
        owner="alice",
        generated_at=datetime.now(tz=UTC),
        parameters={},
        sections=(section, section),
    )

    csv_data = reports.report_to_csv(document).decode()
    assert csv_data.count("# Section: Metrics") == 2


def test_report_to_pdf_generates_output(monkeypatch):
    class FakeCanvas:
        def __init__(self, buffer, pagesize):
            self.buffer = buffer
            self.pagesize = pagesize
            self.calls: list[str] = []

        def setFont(self, *args, **kwargs):
            self.calls.append("setFont")

        def drawString(self, *args, **kwargs):
            self.calls.append("drawString")

        def showPage(self):
            self.calls.append("showPage")

        def save(self):
            self.calls.append("save")

    fake_canvas_mod = SimpleNamespace(Canvas=FakeCanvas)
    monkeypatch.setattr(reports, "canvas", fake_canvas_mod)
    monkeypatch.setattr(reports, "letter", (200, 150))

    schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        description="Portfolio metrics",
        columns=(
            reports.ReportColumnSchema("metric", "Metric"),
            reports.ReportColumnSchema("value", "Value"),
        ),
    )
    section = reports.ReportSectionData(
        schema=schema,
        rows=(
            {"metric": "Owner", "value": 1.2345},
            {"metric": "Empty", "value": None},
        ),
    )
    document = reports.ReportDocument(
        template=reports.ReportTemplate(
            template_id="pdf",
            name="PDF",
            description="",
            sections=(schema,),
            builtin=False,
        ),
        owner="alice",
        generated_at=datetime.now(tz=UTC),
        parameters={"start": "2024-01-01"},
        sections=(section,),
    )

    output = reports.report_to_pdf(document)
    assert isinstance(output, bytes)


def test_report_to_pdf_requires_canvas(monkeypatch):
    monkeypatch.setattr(reports, "canvas", None)
    schema = reports.ALLOCATION_BREAKDOWN_TEMPLATE.sections[0]
    document = reports.ReportDocument(
        template=reports.ALLOCATION_BREAKDOWN_TEMPLATE,
        owner="alice",
        generated_at=datetime.now(tz=UTC),
        parameters={},
        sections=(reports.ReportSectionData(schema=schema, rows=()),),
    )

    with pytest.raises(RuntimeError, match="reportlab is required"):
        reports.report_to_pdf(document)


def test_section_builders_use_context():
    summary = reports.ReportData(
        owner="alice",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        realized_gains_gbp=12.5,
        income_gbp=7.25,
        cumulative_return=0.15,
        max_drawdown=-0.05,
        history=[
            {
                "date": "2024-01-01",
                "value": 100.0,
                "daily_return": 0.01,
                "weekly_return": 0.02,
                "cumulative_return": 0.05,
                "drawdown": 0.0,
            }
        ],
    )

    context = SimpleNamespace(
        summary=lambda: summary,
        transactions=lambda: [{"metric": "Owner"}],
        allocation=lambda: [{"ticker": "ABC", "value": 10.0}],
    )

    metrics_schema = reports.PERFORMANCE_SUMMARY_TEMPLATE.sections[0]
    history_schema = reports.PERFORMANCE_SUMMARY_TEMPLATE.sections[1]
    tx_schema = reports.TRANSACTIONS_TEMPLATE.sections[0]
    alloc_schema = reports.ALLOCATION_BREAKDOWN_TEMPLATE.sections[0]

    metrics_rows = reports._build_metrics_section(context, metrics_schema)
    history_rows = reports._build_history_section(context, history_schema)
    tx_rows = reports._build_transactions_section(context, tx_schema)
    alloc_rows = reports._build_allocation_section(context, alloc_schema)

    assert metrics_rows[0]["metric"] == "Owner"
    assert history_rows[0]["date"] == "2024-01-01"
    assert tx_rows == [{"metric": "Owner"}]
    assert alloc_rows == [{"ticker": "ABC", "value": 10.0}]


def test_build_report_document_includes_parameters(monkeypatch):
    summary = reports.ReportData(
        owner="alice",
        start=date(2024, 1, 1),
        end=date(2024, 1, 31),
        realized_gains_gbp=0.0,
        income_gbp=0.0,
        cumulative_return=None,
        max_drawdown=None,
        history=[],
    )

    context = SimpleNamespace(
        summary=lambda: summary,
        transactions=lambda: [],
        allocation=lambda: [],
    )

    monkeypatch.setattr(reports, "ReportContext", lambda owner, start=None, end=None: context)
    monkeypatch.setattr(reports, "get_template", lambda template_id, store=None: reports.PERFORMANCE_SUMMARY_TEMPLATE)

    start = date(2024, 1, 1)
    end = date(2024, 1, 2)
    document = reports.build_report_document("performance-summary", "alice", start=start, end=end)

    assert document.parameters == {"start": "2024-01-01", "end": "2024-01-02"}

