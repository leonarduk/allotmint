from backend.emails import pension_report


def _sample_report() -> pension_report.PensionReport:
    return pension_report.PensionReport(
        owner_name="Alice",
        stats={"Current pot value": "£10,000.00"},
        scenarios=[{"label": "Base (5.0% growth)", "projected_pot_gbp": "£50,000.00"}],
        alerts=["Pot value dropped 12.0% since the last report."],
    )


def test_render_pension_report_uses_template(monkeypatch):
    captured = {}

    class FakeTemplate:
        def render(self, **context):
            captured.update(context)
            return "<html>rendered</html>"

    monkeypatch.setattr(
        pension_report._env,  # type: ignore[attr-defined]
        "get_template",
        lambda name: FakeTemplate(),
    )

    report = _sample_report()
    html = pension_report.render_pension_report(report)

    assert html == "<html>rendered</html>"
    assert captured == {
        "owner_name": "Alice",
        "stats": {"Current pot value": "£10,000.00"},
        "scenarios": [{"label": "Base (5.0% growth)", "projected_pot_gbp": "£50,000.00"}],
        "alerts": ["Pot value dropped 12.0% since the last report."],
    }


def test_send_pension_report_email(monkeypatch):
    sent = {}

    def fake_render(report):
        return "<html>body</html>"

    class StubSES:
        def send_email(self, **payload):
            sent.update(payload)

    monkeypatch.setattr(pension_report, "render_pension_report", fake_render)
    monkeypatch.setattr(pension_report, "_SENDER_EMAIL", "reports@example.com", raising=False)
    monkeypatch.setattr(pension_report.boto3, "client", lambda service, region_name=None: StubSES())

    pension_report.send_pension_report_email("user@example.com", _sample_report())

    assert sent["Source"] == "reports@example.com"
    assert sent["Destination"] == {"ToAddresses": ["user@example.com"]}
    assert sent["Message"]["Subject"]["Data"] == "Pension Report - Alice"
    assert sent["Message"]["Body"]["Html"]["Data"] == "<html>body</html>"
