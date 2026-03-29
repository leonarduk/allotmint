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
        def __init__(self, buffer, pagesize, **kwargs):
            self.buffer = buffer
            self.pagesize = pagesize
            self.calls: list[str] = []

        def setFont(self, *args, **kwargs):
            self.calls.append("setFont")

        def drawString(self, *args, **kwargs):
            self.calls.append("drawString")

        def drawRightString(self, *args, **kwargs):
            self.calls.append("drawRightString")

        def drawCentredString(self, *args, **kwargs):
            self.calls.append("drawCentredString")

        def setLineWidth(self, *args, **kwargs):
            self.calls.append("setLineWidth")

        def line(self, *args, **kwargs):
            self.calls.append("line")

        def saveState(self):
            self.calls.append("saveState")

        def restoreState(self):
            self.calls.append("restoreState")

        def setFillColorRGB(self, *args, **kwargs):
            self.calls.append("setFillColorRGB")

        def translate(self, *args, **kwargs):
            self.calls.append("translate")

        def rotate(self, *args, **kwargs):
            self.calls.append("rotate")

        def setTitle(self, *args, **kwargs):
            self.calls.append("setTitle")

        def showPage(self):
            self.calls.append("showPage")

        def save(self):
            self.calls.append("save")

        def setPageCompression(self, *args, **kwargs):
            pass

    fake_canvas_mod = SimpleNamespace(Canvas=FakeCanvas)
    monkeypatch.setattr(reports, "canvas", fake_canvas_mod)
    monkeypatch.setattr(reports, "letter", (200, 150))
    monkeypatch.setattr(reports, "Table", None)

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
        parameters={"start": "2024-01-01", "watermark": "SAMPLE"},
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


def test_report_to_pdf_formats_values_and_optional_watermark(monkeypatch):
    class FakeCanvas:
        last_instance = None

        def __init__(self, buffer, pagesize, **kwargs):
            self.calls: list[tuple[str, tuple, dict]] = []
            FakeCanvas.last_instance = self

        def setFont(self, *args, **kwargs):
            self.calls.append(("setFont", args, kwargs))

        def drawString(self, *args, **kwargs):
            self.calls.append(("drawString", args, kwargs))

        def drawRightString(self, *args, **kwargs):
            self.calls.append(("drawRightString", args, kwargs))

        def drawCentredString(self, *args, **kwargs):
            self.calls.append(("drawCentredString", args, kwargs))

        def setLineWidth(self, *args, **kwargs):
            self.calls.append(("setLineWidth", args, kwargs))

        def line(self, *args, **kwargs):
            self.calls.append(("line", args, kwargs))

        def saveState(self):
            self.calls.append(("saveState", (), {}))

        def restoreState(self):
            self.calls.append(("restoreState", (), {}))

        def setFillColorRGB(self, *args, **kwargs):
            self.calls.append(("setFillColorRGB", args, kwargs))

        def translate(self, *args, **kwargs):
            self.calls.append(("translate", args, kwargs))

        def rotate(self, *args, **kwargs):
            self.calls.append(("rotate", args, kwargs))

        def setTitle(self, *args, **kwargs):
            self.calls.append(("setTitle", args, kwargs))

        def showPage(self):
            self.calls.append(("showPage", (), {}))

        def save(self):
            self.calls.append(("save", (), {}))

        def setPageCompression(self, *args, **kwargs):
            pass

    fake_canvas_mod = SimpleNamespace(Canvas=FakeCanvas)
    monkeypatch.setattr(reports, "canvas", fake_canvas_mod)
    monkeypatch.setattr(reports, "letter", (500, 700))
    monkeypatch.setattr(reports, "Table", None)

    schema = reports.ReportSectionSchema(
        id="metrics",
        title="Metrics",
        source="performance.metrics",
        columns=(
            reports.ReportColumnSchema("amount_gbp", "Amount (GBP)", type="number"),
            reports.ReportColumnSchema("daily_return", "Daily return", type="number"),
            reports.ReportColumnSchema("drawdown", "Drawdown", type="number"),
            reports.ReportColumnSchema("portfolio_weight", "Portfolio Weight", type="number"),
            reports.ReportColumnSchema("return_pct", "Return (%)", type="number"),
            reports.ReportColumnSchema("weight_pct", "Weight (%)", type="number"),
        ),
    )
    section = reports.ReportSectionData(
        schema=schema,
        rows=(
            {
                "amount_gbp": 1234.5,
                "daily_return": 0.125,
                "drawdown": -0.05,
                "portfolio_weight": 0.4532,
                "return_pct": 45.32,
                "weight_pct": 45.32,
            },
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
        parameters={"watermark": "SAMPLE"},
        sections=(section,),
    )

    output = reports.report_to_pdf(document)
    assert isinstance(output, bytes)
    calls = FakeCanvas.last_instance.calls
    drawn_values = [args[2] for name, args, _ in calls if name == "drawString" and len(args) >= 3]
    assert any("£1,234.50" in value for value in drawn_values)
    assert any("12.50%" in value for value in drawn_values)
    assert any("-5.00%" in value for value in drawn_values)
    assert any("45.32%" in value for value in drawn_values)
    assert not any("0.4532" in value for value in drawn_values)
    assert not any("4,532.00%" in value for value in drawn_values)
    assert any(
        name == "drawCentredString" and args[-1] == "SAMPLE"
        for name, args, _ in calls
    )


def test_report_to_pdf_key_findings_wrap_across_pages(monkeypatch):
    class FakeCanvas:
        last_instance = None

        def __init__(self, buffer, pagesize, **kwargs):
            self.calls: list[tuple[str, tuple, dict]] = []
            FakeCanvas.last_instance = self

        def setFont(self, *args, **kwargs):
            self.calls.append(("setFont", args, kwargs))

        def drawString(self, *args, **kwargs):
            self.calls.append(("drawString", args, kwargs))

        def drawRightString(self, *args, **kwargs):
            self.calls.append(("drawRightString", args, kwargs))

        def drawCentredString(self, *args, **kwargs):
            self.calls.append(("drawCentredString", args, kwargs))

        def setLineWidth(self, *args, **kwargs):
            self.calls.append(("setLineWidth", args, kwargs))

        def line(self, *args, **kwargs):
            self.calls.append(("line", args, kwargs))

        def saveState(self):
            self.calls.append(("saveState", (), {}))

        def restoreState(self):
            self.calls.append(("restoreState", (), {}))

        def setFillColorRGB(self, *args, **kwargs):
            self.calls.append(("setFillColorRGB", args, kwargs))

        def translate(self, *args, **kwargs):
            self.calls.append(("translate", args, kwargs))

        def rotate(self, *args, **kwargs):
            self.calls.append(("rotate", args, kwargs))

        def setTitle(self, *args, **kwargs):
            self.calls.append(("setTitle", args, kwargs))

        def showPage(self):
            self.calls.append(("showPage", (), {}))

        def save(self):
            self.calls.append(("save", (), {}))

        def stringWidth(self, text, font_name, font_size):
            return len(text) * 12

        def setPageCompression(self, *args, **kwargs):
            pass

    fake_canvas_mod = SimpleNamespace(Canvas=FakeCanvas)
    monkeypatch.setattr(reports, "canvas", fake_canvas_mod)
    monkeypatch.setattr(reports, "letter", (220, 180))
    monkeypatch.setattr(reports, "Table", None)

    key_schema = reports.ReportSectionSchema(
        id="key-findings",
        title="Key Findings",
        source="portfolio.key_findings",
        description="Analyst notes",
        columns=(reports.ReportColumnSchema("finding", "Finding"),),
    )
    section = reports.ReportSectionData(
        schema=key_schema,
        rows=(
            {
                "finding": (
                    "Portfolio remains concentrated in a narrow set of US growth names while "
                    "cash exposure has stayed above the house view for several review cycles"
                )
            },
        ),
    )
    document = reports.ReportDocument(
        template=reports.ReportTemplate(
            template_id="audit-report",
            name="Audit report",
            description="",
            sections=(key_schema,),
            builtin=False,
        ),
        owner="alice",
        generated_at=datetime.now(tz=UTC),
        parameters={},
        sections=(section,),
    )

    output = reports.report_to_pdf(document)

    assert isinstance(output, bytes)
    calls = FakeCanvas.last_instance.calls
    assert sum(1 for name, _, _ in calls if name == "showPage") >= 2
    drawn_values = [args[2] for name, args, _ in calls if name == "drawString" and len(args) >= 3]
    assert drawn_values.count("Key Findings") >= 1
    assert any("Portfolio remains concentrated" in value for value in drawn_values)


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


def test_section_builders_include_portfolio_sources():
    for source in (
        "portfolio.overview",
        "portfolio.sectors",
        "portfolio.regions",
        "portfolio.concentration",
        "portfolio.var",
    ):
        assert source in reports.SECTION_BUILDERS


def test_portfolio_section_builders_use_monkeypatched_dependencies(monkeypatch):
    mock_portfolio = {
        "total_value_estimate_gbp": 1234.56,
        "accounts": [{"id": "acc-1", "holdings": [{"ticker": "AAA"}, {"ticker": "BBB"}]}],
    }
    mock_sectors = [{"sector": "Technology", "market_value_gbp": 700.0}]
    mock_regions = [{"region": "North America", "market_value_gbp": 800.0}]
    mock_tickers = [
        {"ticker": "AAA", "market_value_gbp": 500.0},
        {"ticker": "BBB", "market_value_gbp": 300.0},
    ]

    monkeypatch.setattr(reports, "build_owner_portfolio", lambda owner: mock_portfolio)
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_sector", lambda pf: mock_sectors)
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_region", lambda pf: mock_regions)
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_ticker", lambda pf: mock_tickers)
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence=0.95: {"1d": 0.12} if confidence == 0.95 else {"1d": 0.2},
    )
    monkeypatch.setattr(reports.risk, "compute_sharpe_ratio", lambda owner: 1.75)

    context = reports.ReportContext(owner="alice", start=None, end=None)

    overview = reports._build_portfolio_overview_section(
        context, reports.AUDIT_REPORT_TEMPLATE.sections[0]
    )
    sectors = reports._build_portfolio_sectors_section(
        context, reports.AUDIT_REPORT_TEMPLATE.sections[1]
    )
    regions = reports._build_portfolio_regions_section(
        context, reports.AUDIT_REPORT_TEMPLATE.sections[2]
    )
    concentration = reports._build_portfolio_concentration_section(
        context, reports.AUDIT_REPORT_TEMPLATE.sections[3]
    )
    var_rows = reports._build_portfolio_var_section(
        context, reports.AUDIT_REPORT_TEMPLATE.sections[4]
    )

    assert overview == [{"total_value_gbp": 1234.56, "holdings_count": 2, "accounts_count": 1}]
    assert sectors == [{"sector": "Technology", "value": 700.0, "weight": 1.0}]
    assert regions == [{"region": "North America", "value": 800.0, "weight": 1.0}]
    assert concentration == [
        {"ticker": "AAA", "value": 500.0, "weight": 0.625, "hhi": pytest.approx(0.53125)},
        {"ticker": "BBB", "value": 300.0, "weight": 0.375, "hhi": pytest.approx(0.53125)},
    ]
    assert [row["metric"] for row in var_rows] == ["VaR (95%)", "VaR (99%)", "Sharpe ratio"]
    assert [row["value"] for row in var_rows] == [0.12, 0.2, 1.75]
    assert [row["units"] for row in var_rows] == ["GBP", "GBP", "ratio"]


def test_portfolio_section_builders_reuse_cached_snapshot(monkeypatch):
    snapshot_calls = 0
    mock_portfolio = {
        "total_value_estimate_gbp": 1234.56,
        "accounts": [{"id": "acc-1", "holdings": [{"ticker": "AAA"}, {"ticker": "BBB"}]}],
    }

    def fake_snapshot(owner):
        nonlocal snapshot_calls
        snapshot_calls += 1
        return mock_portfolio

    monkeypatch.setattr(reports, "_portfolio_snapshot", fake_snapshot)
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_sector",
        lambda pf: [{"sector": "Technology", "market_value_gbp": 700.0}],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_region",
        lambda pf: [{"region": "North America", "market_value_gbp": 800.0}],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_ticker",
        lambda pf: [{"ticker": "AAA", "market_value_gbp": 500.0}],
    )
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence=0.95: {"1d": 0.12},
    )
    monkeypatch.setattr(reports.risk, "compute_sharpe_ratio", lambda owner: 1.75)

    document = reports.build_report_document("audit-report", "alice")

    assert len(document.sections) == 5
    assert snapshot_calls == 1


def test_portfolio_section_builders_return_declared_schema_keys(monkeypatch):
    monkeypatch.setattr(
        reports,
        "_portfolio_snapshot",
        lambda owner: {"accounts": [{"holdings": [{"ticker": "AAA"}]}]},
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_sector",
        lambda pf: [{"sector": "Technology", "market_value_gbp": 10.0}],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_region",
        lambda pf: [{"region": "North America", "market_value_gbp": 10.0}],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_ticker",
        lambda pf: [{"ticker": "AAA", "market_value_gbp": 10.0}],
    )
    context = reports.ReportContext(owner="alice", start=None, end=None)

    sectors = reports._build_portfolio_sectors_section(context, reports.AUDIT_REPORT_TEMPLATE.sections[1])
    regions = reports._build_portfolio_regions_section(context, reports.AUDIT_REPORT_TEMPLATE.sections[2])
    concentration = reports._build_portfolio_concentration_section(
        context, reports.AUDIT_REPORT_TEMPLATE.sections[3]
    )

    assert set(sectors[0]) == {"sector", "value", "weight"}
    assert set(regions[0]) == {"region", "value", "weight"}
    assert set(concentration[0]) == {"ticker", "value", "weight", "hhi"}


def test_audit_concentration_hhi_uses_full_holding_set(monkeypatch):
    tickers = [
        {"ticker": f"T{i:02d}", "market_value_gbp": float(120 - i)}
        for i in range(12)
    ]
    monkeypatch.setattr(
        reports,
        "_portfolio_snapshot",
        lambda owner: {"accounts": [{"holdings": [{"ticker": row["ticker"]} for row in tickers]}]},
    )
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_ticker", lambda pf: tickers)
    context = reports.ReportContext(owner="alice", start=None, end=None)

    concentration = reports._build_portfolio_concentration_section(
        context, reports.AUDIT_REPORT_TEMPLATE.sections[3]
    )

    expected_hhi = sum(
        (row["market_value_gbp"] / sum(item["market_value_gbp"] for item in tickers)) ** 2
        for row in tickers
    )
    assert len(concentration) == 10
    assert all(row["hhi"] == pytest.approx(expected_hhi) for row in concentration)


def test_normalise_value_weight_rows_prefers_value_and_sorts_descending():
    rows = reports._normalise_value_weight_rows(
        [
            {"sector": "Healthcare", "value": 30.0, "market_value_gbp": 300.0},
            {"sector": "Technology", "value": 70.0, "market_value_gbp": 700.0},
        ],
        label_key="sector",
    )

    assert rows == [
        {"sector": "Technology", "value": 70.0, "weight": 0.7},
        {"sector": "Healthcare", "value": 30.0, "weight": 0.3},
    ]


def test_normalise_value_weight_rows_uses_weight_pct_and_unknown_label():
    rows = reports._normalise_value_weight_rows(
        [
            {"sector": "", "market_value_gbp": 1000.0, "weight_pct": 75.0},
            {"market_value_gbp": 333.0, "weight_pct": 25.0},
        ],
        label_key="sector",
    )

    assert rows == [
        {"sector": "Unknown", "value": 1000.0, "weight": 0.75},
        {"sector": "Unknown", "value": 333.0, "weight": 0.25},
    ]


def test_portfolio_var_builder_extracts_numeric_from_payload(monkeypatch):
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence=0.95: {
            "window_days": 365,
            "confidence": confidence,
            "1d": 12.3456 if confidence == 0.95 else 23.4567,
            "10d": 40.0 if confidence == 0.95 else 50.0,
        },
    )
    monkeypatch.setattr(reports.risk, "compute_sharpe_ratio", lambda owner: 1.2)
    context = reports.ReportContext(owner="alice", start=None, end=None)

    var_rows = reports._build_portfolio_var_section(context, reports.AUDIT_REPORT_TEMPLATE.sections[4])

    assert var_rows == [
        {"metric": "VaR (95%)", "value": 12.3456, "units": "GBP"},
        {"metric": "VaR (99%)", "value": 23.4567, "units": "GBP"},
        {"metric": "Sharpe ratio", "value": 1.2, "units": "ratio"},
    ]


def test_audit_portfolio_var_builder_returns_empty_when_risk_data_missing(monkeypatch):
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence=0.95: (_ for _ in ()).throw(FileNotFoundError("missing risk data")),
    )
    monkeypatch.setattr(
        reports.risk,
        "compute_sharpe_ratio",
        lambda owner: (_ for _ in ()).throw(FileNotFoundError("missing sharpe data")),
    )
    context = reports.ReportContext(owner="alice", start=None, end=None)

    var_rows = reports._build_portfolio_var_section(context, reports.AUDIT_REPORT_TEMPLATE.sections[4])

    assert var_rows == []


def test_portfolio_overview_counts_nested_holdings(monkeypatch):
    monkeypatch.setattr(
        reports,
        "_portfolio_snapshot",
        lambda owner: {
            "total_value_estimate_gbp": 900.0,
            "accounts": [
                {"id": "a1", "holdings": [{"ticker": "AAA"}, {"ticker": "BBB"}]},
                {"id": "a2", "holdings": [{"ticker": "CCC"}]},
            ],
        },
    )
    context = reports.ReportContext(owner="alice", start=None, end=None)

    overview = reports._build_portfolio_overview_section(context, reports.AUDIT_REPORT_TEMPLATE.sections[0])

    assert overview == [{"total_value_gbp": 900.0, "holdings_count": 3, "accounts_count": 2}]


@pytest.mark.parametrize(
    "builder,section",
    [
        (reports._build_portfolio_overview_section, 0),
        (reports._build_portfolio_sectors_section, 1),
        (reports._build_portfolio_regions_section, 2),
        (reports._build_portfolio_concentration_section, 3),
    ],
)
def test_portfolio_builders_handle_missing_snapshot(monkeypatch, builder, section):
    monkeypatch.setattr(reports, "_portfolio_snapshot", lambda owner: None)
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_sector", lambda pf: [])
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_region", lambda pf: [])
    monkeypatch.setattr(reports.portfolio_utils, "aggregate_by_ticker", lambda pf: [])
    context = reports.ReportContext(owner="alice", start=None, end=None)

    rows = builder(context, reports.AUDIT_REPORT_TEMPLATE.sections[section])

    if section == 0:
        assert rows == [{"total_value_gbp": None, "holdings_count": 0, "accounts_count": 0}]
    else:
        assert rows == []


def test_build_report_document_audit_template_dispatches_real_builders(monkeypatch):
    summary = reports.ReportData(
        owner="alice",
        start=None,
        end=None,
        realized_gains_gbp=0.0,
        income_gbp=0.0,
        cumulative_return=None,
        max_drawdown=None,
        history=[],
    )
    context = SimpleNamespace(
        owner="alice",
        summary=lambda: summary,
        transactions=lambda: [],
        allocation=lambda: [],
        portfolio=lambda: {
            "total_value_estimate_gbp": 200.0,
            "accounts": [{"holdings": [{"ticker": "AAA"}, {"ticker": "BBB"}]}],
        },
    )
    monkeypatch.setattr(reports, "ReportContext", lambda owner, start=None, end=None: context)
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_sector",
        lambda pf: [{"sector": "Technology", "market_value_gbp": 120.0}],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_region",
        lambda pf: [{"region": "North America", "market_value_gbp": 120.0}],
    )
    monkeypatch.setattr(
        reports.portfolio_utils,
        "aggregate_by_ticker",
        lambda pf: [
            {"ticker": "AAA", "market_value_gbp": 120.0},
            {"ticker": "BBB", "market_value_gbp": 80.0},
        ],
    )
    monkeypatch.setattr(
        reports.risk,
        "compute_portfolio_var",
        lambda owner, confidence=0.95: {"1d": 10.0 if confidence == 0.95 else 20.0},
    )
    monkeypatch.setattr(reports.risk, "compute_sharpe_ratio", lambda owner: 1.11)

    document = reports.build_report_document("audit-report", "alice")

    rows_by_source = {
        section.schema.source: list(section.rows)
        for section in document.sections
    }
    assert rows_by_source["portfolio.overview"] == [
        {"total_value_gbp": 200.0, "holdings_count": 2, "accounts_count": 1}
    ]
    assert rows_by_source["portfolio.sectors"] == [
        {"sector": "Technology", "value": 120.0, "weight": 1.0}
    ]
    assert rows_by_source["portfolio.regions"] == [
        {"region": "North America", "value": 120.0, "weight": 1.0}
    ]
    assert rows_by_source["portfolio.concentration"][0]["ticker"] == "AAA"
    assert rows_by_source["portfolio.var"] == [
        {"metric": "VaR (95%)", "value": 10.0, "units": "GBP"},
        {"metric": "VaR (99%)", "value": 20.0, "units": "GBP"},
        {"metric": "Sharpe ratio", "value": 1.11, "units": "ratio"},
    ]


def test_get_template_audit_report_has_expected_order_and_legacy_builtins():
    template = reports.get_template("audit-report")
    assert template is not None
    assert [section.source for section in template.sections] == [
        "portfolio.overview",
        "portfolio.sectors",
        "portfolio.regions",
        "portfolio.concentration",
        "portfolio.var",
        "portfolio.key_findings",
    ]

    metadata = reports.list_template_metadata()
    ids = {item["template_id"] for item in metadata}
    assert "performance-summary" in ids
    assert "transactions" in ids
    assert "allocation-breakdown" in ids
