"""Monthly plan-brief Lambda (#10475): per-owner isolation, plan-less owners, optional email."""

from __future__ import annotations

import pytest

from backend.common.investment_plan import PlanNotFoundError
from backend.lambda_api import plan_brief as lam


@pytest.fixture()
def wiring(monkeypatch, tmp_path):
    sent, alerts, briefed = [], [], []
    portfolios = [
        {"owner": "alex", "person": {"email": "alex@example.com", "full_name": "Alex"}},
        {"owner": "bob", "person": {"email": "bob@example.com"}},
        {"owner": "carol", "person": {}},
    ]

    async def fake_run_brief(owner, accounts_root, **kwargs):
        briefed.append(owner)
        if owner == "bob":
            raise PlanNotFoundError("no plan")
        if owner == "carol":
            raise RuntimeError("broken portfolio")
        return {"owner": owner, "as_of": "2026-11-01"}

    monkeypatch.setattr(lam, "_load_recipient_owners", lambda: None)
    monkeypatch.setattr(lam, "list_portfolios", lambda: portfolios)
    monkeypatch.setattr(lam, "resolve_default_accounts_root", lambda: tmp_path)
    monkeypatch.setattr(lam, "run_brief", fake_run_brief)
    monkeypatch.setattr(lam, "send_plan_brief_email", lambda email, brief, name: sent.append((email, name)))
    monkeypatch.setattr(lam, "publish_sns_alert", alerts.append)
    return {"sent": sent, "alerts": alerts, "briefed": briefed}


def test_handler_briefs_each_owner_and_isolates_failures(wiring, monkeypatch):
    monkeypatch.setenv("PLAN_BRIEF_SEND_EMAIL", "true")
    result = lam.lambda_handler({}, None)

    assert wiring["briefed"] == ["alex", "bob", "carol"]
    assert result["briefs"] == 1
    assert result["errors"] == ["carol: broken portfolio"]
    assert wiring["sent"] == [("alex@example.com", "Alex")]
    assert "carol" in wiring["alerts"][0]["message"]


def test_email_is_off_unless_enabled(wiring, monkeypatch):
    monkeypatch.delenv("PLAN_BRIEF_SEND_EMAIL", raising=False)
    lam.lambda_handler({}, None)
    assert wiring["sent"] == []


def test_recipient_list_limits_owners(wiring, monkeypatch):
    monkeypatch.setattr(lam, "_load_recipient_owners", lambda: ["alex"])
    lam.lambda_handler({}, None)
    assert wiring["briefed"] == ["alex"]


def test_email_renders_drift_triggers_and_disclaimer(plan):
    from backend.common.allocation_policy import AllocationPolicy
    from backend.emails.plan_brief import render_plan_brief
    from backend.plan_brief.agent import _offline
    from backend.plan_brief.drift import build_facts
    from tests.backend.plan_brief.conftest import TODAY, portfolio

    facts = build_facts(plan, portfolio(), AllocationPolicy(targets={"equity": 70.0, "bond": 30.0}), [], TODAY)
    brief = {**facts, **_offline(plan, facts, "not configured"), "as_of": "2026-10-09", "disclaimer": plan.disclaimer}

    html = render_plan_brief(brief, "Alex")

    assert "+6.0pp" in html and "+6,000" in html
    assert "Bank Rate below 3%" in html and "Can&#39;t evaluate" in html
    assert "Review due" in html
    assert "differ from the plan target" in html
    assert "not regulated advice" in html


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('{"owners": ["alex", "bob"]}', ["alex", "bob"]),
        ('["alex"]', ["alex"]),
        # An explicit empty list pauses the job; it does not mean everyone.
        ('{"owners": []}', []),
        ('{"owners": "alex"}', None),
    ],
)
def test_recipient_parameter_shapes(monkeypatch, value, expected):
    monkeypatch.delenv("PLAN_BRIEF_RECIPIENTS_URI", raising=False)

    class Ssm:
        def get_parameter(self, Name, WithDecryption):  # noqa: N803
            return {"Parameter": {"Value": value}}

    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: Ssm())
    assert lam._load_recipient_owners() == expected


def test_missing_recipient_parameter_means_every_owner(monkeypatch):
    """A missing ssm://plan-brief-recipients is swallowed by ParameterStoreJSONStorage.load()."""
    from botocore.exceptions import ClientError

    monkeypatch.delenv("PLAN_BRIEF_RECIPIENTS_URI", raising=False)
    calls = []

    class MissingParameterSsm:
        def get_parameter(self, Name, WithDecryption):  # noqa: N803
            calls.append(Name)
            raise ClientError({"Error": {"Code": "ParameterNotFound", "Message": "nope"}}, "GetParameter")

    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: MissingParameterSsm())

    assert lam._load_recipient_owners() is None
    assert calls == ["plan-brief-recipients"]


def test_empty_recipient_list_briefs_nobody(wiring, monkeypatch):
    monkeypatch.setattr(lam, "_load_recipient_owners", lambda: [])
    assert lam.lambda_handler({}, None) == {"briefs": 0, "errors": []}
    assert wiring["briefed"] == []


def test_explicit_but_unreadable_recipient_list_fails_closed(monkeypatch):
    """A configured URI that gives no list must not brief (and email) every owner."""
    from botocore.exceptions import ClientError

    monkeypatch.setenv("PLAN_BRIEF_RECIPIENTS_URI", "ssm://typo-recipients")

    class Denied:
        def get_parameter(self, Name, WithDecryption):  # noqa: N803
            raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "GetParameter")

    monkeypatch.setattr("boto3.client", lambda service, *args, **kwargs: Denied())
    with pytest.raises(RuntimeError, match="gave no owner list"):
        lam._load_recipient_owners()


def test_unreadable_recipient_list_stops_the_run_with_an_alert(monkeypatch):
    alerts, briefed = [], []

    def boom():
        raise RuntimeError("PLAN_BRIEF_RECIPIENTS_URI ssm://typo gave no owner list")

    monkeypatch.setattr(lam, "_load_recipient_owners", boom)
    monkeypatch.setattr(lam, "list_portfolios", lambda: [{"owner": "alex"}])
    monkeypatch.setattr(lam, "run_brief", lambda *a, **k: briefed.append(a))
    monkeypatch.setattr(lam, "publish_sns_alert", alerts.append)

    result = lam.lambda_handler({}, None)

    assert result["briefs"] == 0 and briefed == []
    assert "failed to start" in alerts[0]["message"]
