import pytest

from backend.lambda_api import pension_report as lam


def _portfolio(owner="alice", dob="1990-01-01", email="alice@example.com", pot=10000.0):
    return {
        "owner": owner,
        "person": {"dob": dob, "email": email, "full_name": owner.title()},
        "accounts": [{"account_type": "sipp", "value_estimate_gbp": pot}],
    }


@pytest.fixture
def stub_environment(monkeypatch):
    monkeypatch.setattr(lam, "_load_recipient_owners", lambda: None)
    monkeypatch.setattr(lam, "get_previous_snapshot", lambda owner: None)
    monkeypatch.setattr(lam, "ytd_baseline_pot_gbp", lambda previous, pot, today: pot)
    monkeypatch.setattr(lam, "previous_period_pot_gbp", lambda previous, pot: pot)
    monkeypatch.setattr(lam, "record_snapshot", lambda owner, *, pot_gbp, as_of: None)

    sent_emails = []
    monkeypatch.setattr(lam, "send_pension_report_email", lambda email, report: sent_emails.append((email, report)))

    alerts = []
    monkeypatch.setattr(lam, "publish_sns_alert", lambda alert: alerts.append(alert))

    return {"sent_emails": sent_emails, "alerts": alerts}


def test_lambda_handler_sends_report_for_each_portfolio(monkeypatch, stub_environment):
    monkeypatch.setattr(lam, "list_portfolios", lambda: [_portfolio()])

    result = lam.lambda_handler({}, {})

    assert result == {"sent": 1, "errors": []}
    assert len(stub_environment["sent_emails"]) == 1
    email, report = stub_environment["sent_emails"][0]
    assert email == "alice@example.com"
    assert report.owner_name == "Alice"
    assert "Current pot value" in report.stats
    assert len(report.scenarios) == 3
    assert stub_environment["alerts"] == []


def test_lambda_handler_skips_owner_missing_email(monkeypatch, stub_environment):
    monkeypatch.setattr(lam, "list_portfolios", lambda: [_portfolio(email=None)])

    result = lam.lambda_handler({}, {})

    assert result == {"sent": 0, "errors": []}
    assert stub_environment["sent_emails"] == []


def test_lambda_handler_filters_by_recipient_owners(monkeypatch, stub_environment):
    monkeypatch.setattr(lam, "_load_recipient_owners", lambda: ["bob"])
    monkeypatch.setattr(
        lam,
        "list_portfolios",
        lambda: [_portfolio(owner="alice"), _portfolio(owner="bob", email="bob@example.com")],
    )

    result = lam.lambda_handler({}, {})

    assert result["sent"] == 1
    assert stub_environment["sent_emails"][0][0] == "bob@example.com"


def test_lambda_handler_continues_after_per_owner_failure(monkeypatch, stub_environment):
    monkeypatch.setattr(
        lam,
        "list_portfolios",
        lambda: [_portfolio(owner="alice"), _portfolio(owner="bob", email="bob@example.com")],
    )

    def failing_send(email, report):
        if email == "alice@example.com":
            raise RuntimeError("SES outage")
        stub_environment["sent_emails"].append((email, report))

    monkeypatch.setattr(lam, "send_pension_report_email", failing_send)

    result = lam.lambda_handler({}, {})

    assert result["sent"] == 1
    assert len(result["errors"]) == 1
    assert "alice" in result["errors"][0]
    assert len(stub_environment["alerts"]) == 1


def test_lambda_handler_publishes_alert_on_initialisation_failure(monkeypatch, stub_environment):
    def raise_error():
        raise RuntimeError("SSM unavailable")

    monkeypatch.setattr(lam, "_load_recipient_owners", raise_error)

    result = lam.lambda_handler({}, {})

    assert result["sent"] == 0
    assert "SSM unavailable" in result["errors"][0]
    assert len(stub_environment["alerts"]) == 1
    assert "failed to start" in stub_environment["alerts"][0]["message"]


def test_build_report_flags_large_drawdown(monkeypatch, stub_environment):
    monkeypatch.setattr(lam, "previous_period_pot_gbp", lambda previous, pot: 20000.0)
    monkeypatch.setattr(lam, "list_portfolios", lambda: [_portfolio(pot=15000.0)])

    lam.lambda_handler({}, {})

    email, report = stub_environment["sent_emails"][0]
    assert any("dropped" in alert for alert in report.alerts)


def test_build_report_flags_shortfall_when_desired_income_configured(monkeypatch, stub_environment):
    monkeypatch.setenv("PENSION_REPORT_DESIRED_INCOME_ANNUAL", "8000")
    monkeypatch.setattr(lam, "list_portfolios", lambda: [_portfolio(pot=1000.0)])

    lam.lambda_handler({}, {})

    email, report = stub_environment["sent_emails"][0]
    assert any("short of the" in alert for alert in report.alerts)
