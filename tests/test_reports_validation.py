import pytest

import backend.reports as reports


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("example", "example"),
        ("  trimmed-id  ", "trimmed-id"),
        ("alpha_NUM-123", "alpha_NUM-123"),
    ],
)
def test_validate_template_id_accepts_valid_identifiers(raw, expected):
    assert reports._validate_template_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "  ", "invalid id", "too*many"],
)
def test_validate_template_id_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        reports._validate_template_id(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("metrics", "metrics"),
        ("  allocations ", "allocations"),
        ("section-01", "section-01"),
    ],
)
def test_validate_section_id_accepts_valid_identifiers(raw, expected):
    assert reports._validate_section_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "with spaces", "unicode☃"],
)
def test_validate_section_id_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        reports._validate_section_id(raw)


@pytest.mark.parametrize(
    "value, digits, expected",
    [
        (10, 2, 10.0),
        ("3.14159", 3, 3.142),
        (None, 2, None),
        ("not-a-number", 2, None),
    ],
)
def test_round_if_number_handles_numeric_inputs(value, digits, expected):
    assert reports._round_if_number(value, digits) == expected


@pytest.mark.parametrize(
    "item, start, end, expected",
    [
        (
            {
                "date": "2024-01-05",
                "type": "buy",
                "amount_minor": 2500,
                "currency": "usd",
                "description": " Purchase ",
            },
            None,
            None,
            {
                "date": "2024-01-05",
                "type": "BUY",
                "description": "Purchase",
                "amount_gbp": 25.0,
                "currency": "USD",
            },
        ),
        (
            {
                "date": "2024-02-10",
                "type": "sell",
                "amount_minor": "oops",
                "symbol": "Example plc",
            },
            None,
            None,
            {
                "date": "2024-02-10",
                "type": "SELL",
                "description": "Example plc",
                "amount_gbp": 0.0,
                "currency": "GBP",
            },
        ),
    ],
)
def test_normalise_transaction_converts_fields(item, start, end, expected):
    assert reports._normalise_transaction(item, start, end) == expected


def test_normalise_transaction_filters_outside_window():
    item = {"date": "2024-03-01", "type": "buy", "amount_minor": 100}
    start = reports.date(2024, 3, 10)
    end = reports.date(2024, 3, 20)

    assert reports._normalise_transaction(item, start, end) is None

    within_window = {"date": "2024-03-15", "type": "buy", "amount_minor": 100}
    assert reports._normalise_transaction(within_window, start, end) == {
        "date": "2024-03-15",
        "type": "BUY",
        "description": "",
        "amount_gbp": 1.0,
        "currency": "GBP",
    }


def test_normalise_transaction_end_filter_excludes_future_dates():
    item = {"date": "2024-04-01", "type": "sell", "amount_minor": 100}
    end = reports.date(2024, 3, 31)

    assert reports._normalise_transaction(item, None, end) is None


def _example_section(source: str):
    return {
        "id": "metrics",
        "title": " Metrics ",
        "source": source,
        "description": "  Portfolio metrics  ",
        "columns": [
            {"key": "metric", "label": "", "type": "string"},
            {"key": "value"},
        ],
    }


def test_validate_template_payload_normalises_structure():
    payload = {
        "template_id": "  custom-template  ",
        "name": "  Custom Report  ",
        "description": "  Example description  ",
        "sections": [_example_section("performance.metrics")],
    }

    result = reports._validate_template_payload(payload)

    assert result["template_id"] == "custom-template"
    assert result["name"] == "Custom Report"
    section = result["sections"][0]
    assert section["description"] == "Portfolio metrics"
    assert section["columns"] == [
        {"key": "metric", "label": "metric", "type": "string"},
        {"key": "value", "label": "value", "type": "string"},
    ]


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda section: section.update({"id": ""}), "section id"),
        (lambda section: section.update({"source": "unknown"}), "Unsupported section source"),
        (
            lambda section: section.update({"columns": ["oops"]}),
            "columns must be objects",
        ),
        (
            lambda section: section.update({"columns": [{"key": "metric"}, {"key": "metric"}]}),
            "duplicate column",
        ),
    ],
)
def test_validate_template_payload_reports_section_errors(mutator, message):
    section = _example_section("performance.metrics")
    mutator(section)
    payload = {
        "template_id": "custom",
        "name": "Example",
        "sections": [section],
    }

    with pytest.raises(ValueError) as excinfo:
        reports._validate_template_payload(payload)

    assert message in str(excinfo.value)


def test_validate_template_payload_rejects_duplicate_sections():
    section = _example_section("performance.metrics")
    payload = {
        "template_id": "custom",
        "name": "Example",
        "sections": [section, dict(section)],
    }

    with pytest.raises(ValueError, match="Duplicate section id"):
        reports._validate_template_payload(payload)


def test_materialise_template_creates_schema_objects():
    definition = reports._validate_template_payload(
        {
            "template_id": "custom",
            "name": "Example",
            "sections": [_example_section("performance.metrics")],
        }
    )

    template = reports._materialise_template(definition, builtin=False)

    assert template.template_id == "custom"
    assert template.builtin is False
    assert template.sections[0].id == "metrics"
    assert template.sections[0].columns[0].label == "metric"


def test_validate_template_payload_requires_object_payload():
    with pytest.raises(ValueError, match="JSON object"):
        reports._validate_template_payload("not-a-dict")


def test_validate_template_payload_requires_sections_list():
    payload = {"template_id": "custom", "name": "Example", "sections": None}

    with pytest.raises(ValueError, match="at least one section"):
        reports._validate_template_payload(payload)


def test_validate_template_payload_requires_section_objects():
    payload = {"template_id": "custom", "name": "Example", "sections": ["oops"]}

    with pytest.raises(ValueError, match="must be a JSON object"):
        reports._validate_template_payload(payload)


def test_validate_template_payload_requires_section_title():
    section = _example_section("performance.metrics")
    section.pop("title")
    payload = {"template_id": "custom", "name": "Example", "sections": [section]}

    with pytest.raises(ValueError, match="requires a title"):
        reports._validate_template_payload(payload)


def test_validate_template_payload_requires_columns_list():
    section = _example_section("performance.metrics")
    section["columns"] = None
    payload = {"template_id": "custom", "name": "Example", "sections": [section]}

    with pytest.raises(ValueError, match="must define at least one column"):
        reports._validate_template_payload(payload)


def test_validate_template_payload_requires_column_key():
    section = _example_section("performance.metrics")
    section["columns"] = [{"label": "Metric"}]
    payload = {"template_id": "custom", "name": "Example", "sections": [section]}

    with pytest.raises(ValueError, match="column missing key"):
        reports._validate_template_payload(payload)


def test_validate_template_payload_default_column_type_for_blank():
    section = _example_section("performance.metrics")
    section["columns"][0]["type"] = "  "
    payload = {"template_id": "custom", "name": "Example", "sections": [section]}

    result = reports._validate_template_payload(payload)

    assert result["sections"][0]["columns"][0]["type"] == "string"
