"""Statement extraction (#10474). The LLM is always mocked; documents are synthetic."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import httpx
import pytest
from reportlab.pdfgen import canvas

from backend.reconciliation import extract
from backend.reconciliation.models import RawStatement

# What a model would return for the synthetic contract note below.
CONTRACT_NOTE_JSON = {
    "document_type": "contract_note",
    "period_start": None,
    "period_end": None,
    "rows": [
        {
            "date": "2026-01-10",
            "type": "BUY",
            "description": "BP PLC Ordinary 25p",
            "ticker": "BP.",
            "isin": "GB0007980591",
            "units": 200,
            "price": 500,
            "price_unit": "GBX",
            "consideration": 1000.00,
            "fees": 11.95,
            "stamp_duty": 5.00,
            "amount": 1016.95,
        }
    ],
    "closing_holdings": [],
}


def _pdf(lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for offset, line in enumerate(lines):
        pdf.drawString(72, 760 - offset * 16, line)
    pdf.save()
    return buffer.getvalue()


def _scanned_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.rect(72, 600, 300, 100, fill=1)  # an image-like page with no text layer
    pdf.save()
    return buffer.getvalue()


SYNTHETIC_CONTRACT_NOTE = [
    "Synthetic Broker - Contract Note (test fixture, not a real statement)",
    "Trade date 10/01/2026  Settlement 14/01/2026",
    "Bought 200 BP PLC Ordinary 25p at 500.00p",
    "Consideration 1,000.00  Commission 11.95  Stamp duty 5.00  Total 1,016.95",
]


def _extraction(payload: dict):
    return extract.normalise_statement(RawStatement.model_validate(payload))


def test_pdf_text_layer_is_read():
    text = extract.extract_document_text(_pdf(SYNTHETIC_CONTRACT_NOTE), "note.pdf")

    assert "Contract Note" in text
    assert "1,016.95" in text


def test_scanned_pdf_is_unsupported():
    with pytest.raises(extract.UnsupportedDocument, match="scanned"):
        extract.extract_document_text(_scanned_pdf(), "scan.pdf")


def test_corrupt_pdf_is_unsupported():
    with pytest.raises(extract.UnsupportedDocument):
        extract.extract_document_text(b"%PDF-1.4 not really a pdf", "broken.pdf")


def test_csv_is_decoded():
    assert extract.extract_document_text(b"\xef\xbb\xbfDate,Type\n2026-01-01,INTEREST\n", "s.csv").startswith("Date")


def test_binary_non_pdf_is_unsupported():
    with pytest.raises(extract.UnsupportedDocument):
        extract.extract_document_text(b"\xff\xfe\x00\x81", "s.xlsx")


def test_oversized_document_is_unsupported():
    with pytest.raises(extract.UnsupportedDocument, match="too long"):
        extract.extract_document_text(b"x" * (extract.MAX_DOCUMENT_CHARS + 1), "s.txt")


def test_model_output_in_a_code_fence_is_accepted():
    raw = "Here you go:\n```json\n" + json.dumps(CONTRACT_NOTE_JSON) + "\n```"

    parsed = extract.parse_model_output(raw)

    assert parsed.rows[0].units == 200


def test_non_json_model_output_is_rejected():
    with pytest.raises(extract.ExtractionError, match="JSON object"):
        extract.parse_model_output("I could not read this document")


def test_schema_error_names_fields_but_not_values():
    payload = {**CONTRACT_NOTE_JSON, "rows": [{**CONTRACT_NOTE_JSON["rows"][0], "type": "SWAP", "units": -987654}]}

    with pytest.raises(extract.ExtractionError) as excinfo:
        extract.parse_model_output(json.dumps(payload))

    message = str(excinfo.value)
    assert "rows.0.type" in message and "rows.0.units" in message
    assert "987654" not in message


def test_contract_note_passes_arithmetic_and_is_normalised_to_pence():
    extraction = _extraction(CONTRACT_NOTE_JSON)

    row = extraction.rows[0]
    assert row.flags == []
    assert extraction.warnings == []
    assert row.ticker == "BP.L"
    assert row.price_gbp == 5.0
    assert row.consideration_minor == 100_000
    assert row.fees_minor == 1_695  # commission + stamp duty
    assert row.amount_minor == 101_695


def test_consideration_that_does_not_equal_units_times_price_is_flagged():
    bad = {
        **CONTRACT_NOTE_JSON["rows"][0],
        "price": 5,
        "price_unit": "GBP",
        "consideration": 1100.00,
        "amount": 1116.95,
    }

    extraction = _extraction({**CONTRACT_NOTE_JSON, "rows": [bad]})

    assert "units x price does not equal the consideration" in extraction.rows[0].flags
    assert extraction.warnings and extraction.warnings[0].startswith("Row 1")


def test_total_that_does_not_add_up_is_flagged():
    bad = {**CONTRACT_NOTE_JSON["rows"][0], "amount": 1000.00}

    extraction = _extraction({**CONTRACT_NOTE_JSON, "rows": [bad]})

    assert extraction.rows[0].flags == ["consideration and charges do not add up to the settled total"]


def test_sell_total_subtracts_charges():
    sell = {**CONTRACT_NOTE_JSON["rows"][0], "type": "SELL", "stamp_duty": None, "amount": 988.05}

    assert _extraction({**CONTRACT_NOTE_JSON, "rows": [sell]}).rows[0].flags == []


def test_cash_row_without_amount_is_flagged():
    extraction = _extraction({"rows": [{"date": "2026-02-01", "type": "INTEREST"}]})

    assert extraction.rows[0].flags == ["cash row has no amount"]


def test_opening_plus_flows_must_equal_closing_cash():
    payload = {
        "opening_cash": 100,
        "closing_cash": 150,
        "rows": [{"date": "2026-02-01", "type": "DEPOSIT", "amount": 40}],
    }

    extraction = _extraction(payload)

    assert any("does not add up" in w and "£140.00" in w and "£150.00" in w for w in extraction.warnings)


def test_balanced_cash_has_no_warning():
    payload = {
        "opening_cash": 100,
        "closing_cash": 87.55,
        "rows": [
            {"date": "2026-02-01", "type": "INTEREST", "amount": 0.50},
            {"date": "2026-02-02", "type": "FEES", "amount": 12.95},
        ],
    }

    assert _extraction(payload).warnings == []


def test_is_cloud_provider():
    assert extract.is_cloud_provider("bedrock")
    assert extract.is_cloud_provider("deepseek")
    assert not extract.is_cloud_provider("ollama")


@pytest.mark.asyncio
async def test_extract_statement_from_synthetic_pdf(monkeypatch):
    seen = {}

    async def fake_complete(text, cfg):
        seen["text"] = text
        return json.dumps(CONTRACT_NOTE_JSON)

    monkeypatch.setattr(extract, "complete_extraction", fake_complete)

    extraction = await extract.extract_statement(_pdf(SYNTHETIC_CONTRACT_NOTE), "note.pdf", SimpleNamespace())

    assert "Bought 200 BP PLC" in seen["text"]
    assert len(extraction.rows) == 1 and extraction.rows[0].flags == []


@pytest.mark.asyncio
async def test_extract_statement_does_not_log_extracted_values(monkeypatch, caplog):
    async def fake_complete(text, cfg):
        return json.dumps(CONTRACT_NOTE_JSON)

    monkeypatch.setattr(extract, "complete_extraction", fake_complete)

    with caplog.at_level("DEBUG"):
        await extract.extract_statement(_pdf(SYNTHETIC_CONTRACT_NOTE), "note.pdf", SimpleNamespace())

    assert "1016.95" not in caplog.text and "1,016.95" not in caplog.text and "BP" not in caplog.text


def _cfg(**overrides):
    base = dict(
        chat_provider="ollama", app_env="local", chat_base_url=None, chat_model=None, bedrock_model_id="model-x"
    )
    return SimpleNamespace(**{**base, **overrides})


@pytest.mark.asyncio
async def test_openai_compat_completion_requests_json(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        extract.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)
    )

    reply = await extract.complete_extraction("TEXT", _cfg())

    assert reply == "{}"
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["messages"][0]["content"].endswith("TEXT")


@pytest.mark.asyncio
async def test_deepseek_requires_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(extract.ExtractionError, match="DEEPSEEK_API_KEY"):
        await extract.complete_extraction("TEXT", _cfg(chat_provider="deepseek"))


@pytest.mark.asyncio
async def test_bedrock_completion_uses_converse_without_tools(monkeypatch):
    from backend.chat import bedrock_agent

    captured = {}

    async def fake_converse(client, **kwargs):
        captured.update(kwargs)
        return {"output": {"message": {"content": [{"text": '{"rows": []}'}]}}}

    monkeypatch.setattr(bedrock_agent, "_converse_with_retry", fake_converse)
    monkeypatch.setattr(bedrock_agent, "_bedrock_client", lambda: object())

    reply = await extract.complete_extraction("TEXT", _cfg(chat_provider="bedrock"))

    assert reply == '{"rows": []}'
    assert captured["modelId"] == "model-x"
    assert "toolConfig" not in captured
