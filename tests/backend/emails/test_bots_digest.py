"""Bots digest email, Telegram text and immediate alerts (#10485). Synthetic data only."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.bots import digest_delivery
from backend.bots.digest_models import BotStatus, Digest, DigestEntry, DigestItem, Severity
from backend.bots.digest_settings import DigestSettings
from backend.emails import bots_digest

NOW = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)


def _entry(key, title, summary="", status="new", severity=Severity.HIGH, link=None, bot="cash"):
    return DigestEntry(
        id=key,
        bot=bot,
        owner="alex",
        severity=severity,
        title=title,
        summary=summary,
        link=link,
        action_required=True,
        created=NOW,
        dedupe_key=key,
        status=status,
    )


def _digest():
    return Digest(
        owner="alex",
        generated_at=NOW,
        opener="2 items need you. Cash of £12,345.67 is waiting.",
        items=[
            _entry("cash:t3", "Tranche 3 due Monday", "£5,000 to invest; 1,200 GBP left over", link="/bots"),
            _entry("guardian:sept", "September contribution not received", status="still_open", bot="guardian"),
        ],
        resolved=[_entry("journal:x", "Decision logged", status="resolved", bot="journal")],
        bots=[BotStatus(bot="journal", name="Decision journal", state="not_run_yet")],
    )


@pytest.mark.parametrize(
    "text",
    ["£12,345.67", "£ 5k", "$300", "€1.5m", "1,200 GBP", "-£40", "GBP 5,000", "usd 12.50", "EUR1.2m"],
)
def test_amounts_are_redacted(text):
    assert digest_delivery.redact_amounts(f"x {text} y").count(digest_delivery.HIDDEN_AMOUNT) == 1


def test_percentages_and_dates_are_kept():
    text = "Equity 4.1pp over target; statement uploaded 3 Oct; 12% drift"
    assert digest_delivery.redact_amounts(text) == text


def test_email_has_no_balances_by_default():
    html = bots_digest.render_bots_digest(_digest())
    assert "£" not in html and "GBP" not in html
    assert "12,345" not in html and "5,000" not in html
    assert digest_delivery.HIDDEN_AMOUNT in html
    assert "Tranche 3 due Monday" in html
    assert "Still open" in html and "New" in html
    assert "Decision logged" in html
    assert "Not run yet: Decision journal" in html


def test_email_includes_balances_when_opted_in():
    html = bots_digest.render_bots_digest(_digest(), include_balances=True)
    assert "£12,345.67" in html
    assert "£5,000" in html


def test_email_escapes_item_text_and_drops_unsafe_links():
    digest = _digest()
    digest.items[0] = _entry("cash:x", "<script>alert(1)</script>", link="javascript:alert(1)")
    html = bots_digest.render_bots_digest(digest)
    assert "<script>" not in html
    assert "javascript:" not in html


def test_send_bots_digest_email_uses_ses(monkeypatch):
    sent = {}

    class StubSES:
        def send_email(self, **payload):
            sent.update(payload)

    monkeypatch.setattr(bots_digest.boto3, "client", lambda *a, **k: StubSES())
    monkeypatch.setattr(bots_digest, "_SENDER_EMAIL", "reports@example.com", raising=False)
    bots_digest.send_bots_digest_email("alex@example.com", _digest())
    assert sent["Destination"] == {"ToAddresses": ["alex@example.com"]}
    assert sent["Message"]["Subject"]["Data"] == "Bots digest - 2 items need you"
    assert "£" not in sent["Message"]["Body"]["Html"]["Data"]


def test_telegram_text_redacts_by_default():
    text = digest_delivery.digest_text(_digest(), DigestSettings())
    assert "£" not in text
    assert "NEW [high] Tranche 3 due Monday" in text
    opted_in = digest_delivery.digest_text(_digest(), DigestSettings(include_balances=True))
    assert "£12,345.67" in opted_in


# --- immediate alerts -------------------------------------------------------


@pytest.fixture()
def digests_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTS_DIGESTS_URI", str(tmp_path))
    return tmp_path


def _item(key, bot="guardian", severity=Severity.HIGH):
    return DigestItem(
        id=key, bot=bot, owner="alex", severity=severity, title=f"{key} found", created=NOW, dedupe_key=key
    )


def test_immediate_alert_sent_once_per_open_key(digests_dir):
    settings = DigestSettings(alert_immediately_for={"guardian": [Severity.HIGH]})
    messages = []
    items = [_item("guardian:sept"), _item("guardian:low", severity=Severity.LOW), _item("cash:t3", bot="cash")]

    sent = digest_delivery.send_immediate_alerts("alex", items, settings, send=messages.append)
    assert sent == ["guardian:sept"]
    assert messages == ["[high] guardian:sept found"]

    # Still open: no repeat alert.
    assert digest_delivery.send_immediate_alerts("alex", items, settings, send=messages.append) == []
    # Closed then reopened: alerts again.
    digest_delivery.send_immediate_alerts("alex", [], settings, send=messages.append)
    assert digest_delivery.send_immediate_alerts("alex", items, settings, send=messages.append) == ["guardian:sept"]


def test_no_immediate_alerts_by_default(digests_dir):
    messages = []
    sent = digest_delivery.send_immediate_alerts("alex", [_item("guardian:sept")], DigestSettings(), messages.append)
    assert sent == [] and messages == []


def test_failed_immediate_alert_is_retried(digests_dir):
    settings = DigestSettings(alert_immediately_for={"guardian": [Severity.HIGH]})

    def broken(message):
        raise RuntimeError("telegram down")

    assert digest_delivery.send_immediate_alerts("alex", [_item("guardian:sept")], settings, send=broken) == []
    messages = []
    assert digest_delivery.send_immediate_alerts("alex", [_item("guardian:sept")], settings, messages.append) == [
        "guardian:sept"
    ]


def test_default_sender_uses_trading_agent_transport(monkeypatch):
    from backend.agent import trading_agent

    calls = []
    monkeypatch.setattr(trading_agent, "send_trade_alert", lambda message: calls.append(message))
    digest_delivery.send_digest_telegram(_digest(), DigestSettings())
    assert len(calls) == 1 and calls[0].startswith("AllotMint bots digest for alex")
