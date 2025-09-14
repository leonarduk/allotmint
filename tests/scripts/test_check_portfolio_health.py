from pathlib import Path

import pytest
import scripts.check_portfolio_health as cph


def test_notify_slack_no_webhook(monkeypatch):
    """requests.post is not called when webhook env var missing."""
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    calls: list = []
    monkeypatch.setattr(cph.requests, "post", lambda *a, **k: calls.append((a, k)))
    cph.notify_slack("hello")
    assert calls == []


def test_notify_slack_with_webhook(monkeypatch):
    """requests.post is invoked with proper payload when webhook set."""
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://example.com")
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cph.requests, "post", fake_post)
    cph.notify_slack("hi")
    assert captured["url"] == "http://example.com"
    assert captured["kwargs"]["json"] == {"text": "hi"}


def test_run_check_drawdown_and_missing(monkeypatch, tmp_path):
    publish_calls: list = []
    slack_calls: list = []

    monkeypatch.setattr(cph, "publish_alert", lambda msg: publish_calls.append(msg))
    monkeypatch.setattr(cph, "notify_slack", lambda msg: slack_calls.append(msg))

    monkeypatch.setattr(cph.portfolio, "list_owners", lambda: ["alice", "bob"])
    dd_map = {"alice": -0.3, "bob": None}
    monkeypatch.setattr(cph.portfolio_utils, "compute_max_drawdown", lambda owner: dd_map[owner])

    monkeypatch.setattr(cph.group_portfolio, "list_groups", lambda: [{"slug": "grp1"}])
    monkeypatch.setattr(cph.portfolio_utils, "compute_group_max_drawdown", lambda slug: -0.25)

    def fake_approvals_path(owner: str) -> Path:
        if owner == "alice":
            return tmp_path / owner / "approvals.json"
        raise FileNotFoundError

    monkeypatch.setattr(cph.approvals, "_approvals_path", fake_approvals_path)
    monkeypatch.setattr(cph.portfolio_utils, "_MISSING_META", {"missing/meta.json"}, raising=False)

    findings = cph.run_check(0.2)

    assert any(f["type"] == "owner" and f["name"] == "alice" and f["alert"] for f in findings)
    assert any(f["type"] == "owner" and f["name"] == "bob" and f["drawdown"] is None for f in findings)
    assert any(f["type"] == "group" and f["name"] == "grp1" and f["alert"] for f in findings)
    assert any(f["type"] == "missing_approvals" and f["owner"] == "alice" for f in findings)
    assert any(f["type"] == "missing_metadata" for f in findings)

    assert len(publish_calls) == 2
    assert len(slack_calls) == 2
