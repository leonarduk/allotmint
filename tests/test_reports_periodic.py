"""The periodic-summary report: section rows, insight rules and rendering.

Returns come from the hand-checkable ledger in
``tests/backend/common/test_ledger_performance.py`` (January +10%, February
-8.64% around a mid-month deposit and a dividend, YTD +0.5%). The benchmark
closes below are synthetic.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import report_periodic as rp
from backend import reports
from backend.common import ledger_performance as lp
from backend.routes import reports as reports_route
from tests.backend.common.test_ledger_performance import FEB_RETURN, TRANSACTIONS, fake_loader

END = date(2026, 2, 28)
BENCHMARK = pd.Series(
    {
        pd.Timestamp("2025-02-28"): 80.0,
        pd.Timestamp("2025-12-31"): 100.0,
        pd.Timestamp("2026-01-28"): 101.0,
        pd.Timestamp("2026-01-30"): 102.0,
        pd.Timestamp("2026-02-27"): 104.04,
    }
)


@pytest.fixture
def perf():
    ledger = lp.AccountLedger("isa", TRANSACTIONS, True)
    return lp.build_ledger_performance([ledger], END, price_loader=fake_loader())


def _by(rows, key, value):
    return next(row for row in rows if row[key] == value)


# ──────────────────────────────────────────────────────────────
# Section rows
# ──────────────────────────────────────────────────────────────
def test_period_rows(perf):
    rows = rp.period_rows(perf, BENCHMARK, END)

    assert [(row["period_key"], row["period"]) for row in rows] == [
        ("month", "Feb 2026"),
        ("ytd", "YTD 2026"),
        ("1y", "1 year"),
        ("inception", "Since inception"),
        ("inception_annualised", "Since inception p.a."),
    ]
    month = rows[0]
    assert (month["start"], month["end"]) == ("2026-02-01", "2026-02-28")
    assert month["portfolio_return"] == pytest.approx(FEB_RETURN, abs=1e-6)
    assert month["benchmark_return"] == pytest.approx(0.02, abs=1e-6)
    assert month["excess_return"] == pytest.approx(FEB_RETURN - 0.02, abs=1e-6)
    # YTD and 1Y cannot start before inception; the benchmark is measured from
    # the same base so the comparison is like for like.
    ytd = rows[1]
    assert ytd["start"] == "2026-01-29"
    assert ytd["portfolio_return"] == pytest.approx(0.005, abs=1e-6)
    assert ytd["benchmark_return"] == pytest.approx(104.04 / 101 - 1, abs=1e-6)
    assert rows[2]["start"] == rows[3]["start"] == "2026-01-29"
    # Under a year since inception: no annualised figure.
    assert rows[4]["portfolio_return"] is None
    assert rows[4]["benchmark_return"] is None


def test_period_rows_without_ledger_still_report_the_benchmark():
    rows = rp.period_rows(None, BENCHMARK, END)

    assert all(row["portfolio_return"] is None and row["excess_return"] is None for row in rows)
    assert rows[1]["benchmark_return"] == pytest.approx(0.0404, abs=1e-6)
    assert rows[2]["benchmark_return"] == pytest.approx(104.04 / 80 - 1, abs=1e-6)
    assert rows[3]["start"] is None and rows[3]["benchmark_return"] is None


def test_period_rows_without_benchmark_have_null_benchmark_columns(perf):
    rows = rp.period_rows(perf, None, END)

    assert all(row["benchmark_return"] is None and row["excess_return"] is None for row in rows)
    assert rows[0]["portfolio_return"] is not None


def test_month_to_date_label():
    periods = rp.reporting_periods(date(2026, 2, 13), date(2020, 1, 1))

    assert periods[0].label == "Feb 2026 (MTD)"
    assert periods[0].base == date(2026, 1, 31)


def test_monthly_rows(perf):
    rows = rp.monthly_rows(perf, BENCHMARK, END)

    assert [row["month"] for row in rows][0] == "2025-03"
    assert len(rows) == 12
    jan, feb = _by(rows, "month", "2026-01"), _by(rows, "month", "2026-02")
    assert jan["portfolio_return"] == pytest.approx(0.10, abs=1e-6)
    assert jan["cumulative_ytd_return"] == pytest.approx(0.10, abs=1e-6)
    assert jan["benchmark_return"] == pytest.approx(0.02, abs=1e-6)
    assert feb["portfolio_return"] == pytest.approx(FEB_RETURN, abs=1e-6)
    assert feb["cumulative_ytd_return"] == pytest.approx(0.005, abs=1e-6)
    before = _by(rows, "month", "2025-12")
    assert before["portfolio_return"] is None and before["cumulative_ytd_return"] is None


def test_risk_rows(perf):
    rows = rp.risk_rows(perf, END, 0.01)

    vol = _by(rows, "key", "volatility")
    assert vol["value"] == pytest.approx(perf.returns.std(ddof=1) * 252**0.5, abs=1e-6)
    assert (vol["units"], vol["window"]) == ("fraction", "1Y")
    assert _by(rows, "key", "sharpe")["units"] == "number"
    max_dd = [row for row in rows if row["metric"] == "Max drawdown"]
    assert [row["window"] for row in max_dd] == ["1Y", "Since inception"]
    assert max_dd[1]["value"] == pytest.approx(-0.10, abs=1e-6)
    assert (max_dd[1]["peak_date"], max_dd[1]["trough_date"]) == ("2026-01-30", "2026-02-12")
    current = _by(rows, "key", "current_drawdown")
    assert current["value"] == pytest.approx(0.9 * 2010 / 1980 - 1, abs=1e-6)
    assert current["peak_date"] == "2026-01-30"
    assert rp.risk_rows(None, END, 0.01) == []


def test_contributor_rows(perf):
    rows = rp.contributor_rows(perf, END)

    feb = [row for row in rows if row["period_key"] == "month"]
    assert [(row["direction"], row["ticker"]) for row in feb] == [("Bottom", "AAA.L")]
    assert feb[0]["contribution_gbp"] == pytest.approx(-220.0)
    assert feb[0]["contribution_return"] == pytest.approx(-0.1, abs=1e-6)
    assert feb[0]["weight"] == pytest.approx(1980 / 2010, abs=1e-6)
    ytd = [row for row in rows if row["period_key"] == "ytd"]
    # +100 in January, -220 in February.
    assert [(row["direction"], row["contribution_gbp"]) for row in ytd] == [("Bottom", -120.0)]
    assert rp.contributor_rows(None, END) == []


def test_contributors_rank_top_and_bottom_three():
    index = pd.bdate_range("2026-02-02", periods=2)
    pnl = pd.DataFrame(
        [[0.0] * 7, [50.0, 40.0, 30.0, 20.0, -10.0, -20.0, -30.0]],
        index=index,
        columns=["A", "B", "C", "D", "E", "F", "G"],
    )
    perf = lp.LedgerPerformance(
        inception=date(2026, 2, 2),
        end=date(2026, 2, 3),
        values=pd.Series([1000.0, 1080.0], index=index),
        returns=pd.Series([0.0, 0.08], index=index),
        denominators=pd.Series([1000.0, 1000.0], index=index),
        cash=pd.Series([0.0, 0.0], index=index),
        instrument_values=pd.DataFrame(0.0, index=index, columns=pnl.columns),
        instrument_pnl=pnl,
    )

    rows = rp.contributor_rows(perf, date(2026, 2, 3))
    month = [row for row in rows if row["period_key"] == "month"]

    assert [(row["direction"], row["rank"], row["ticker"]) for row in month] == [
        ("Top", 1, "A"),
        ("Top", 2, "B"),
        ("Top", 3, "C"),
        ("Bottom", 1, "G"),
        ("Bottom", 2, "F"),
        ("Bottom", 3, "E"),
    ]


# ──────────────────────────────────────────────────────────────
# Insight rules: each fires at its threshold and not just short of it
# ──────────────────────────────────────────────────────────────
def _periods(month=0.0, ytd_portfolio=0.10, ytd_benchmark=0.05):
    return [
        {"period_key": "month", "portfolio_return": month},
        {
            "period_key": "ytd",
            "portfolio_return": ytd_portfolio,
            "benchmark_return": ytd_benchmark,
            "excess_return": ytd_portfolio - ytd_benchmark,
        },
    ]


def _assert_boundary(monkeypatch, rule, constant, value, inputs):
    """``rule`` fires with ``constant`` set to the measured ``value`` but not just above it."""
    monkeypatch.setattr(rp, constant, value)
    assert rule(inputs)
    monkeypatch.setattr(rp, constant, value + 1e-9)
    assert rule(inputs) is None


def test_rule_benchmark_gap(monkeypatch):
    behind = rp.InsightInputs(periods=_periods(ytd_portfolio=0.05, ytd_benchmark=0.08), benchmark="VWRL.L")
    _assert_boundary(monkeypatch, rp.rule_benchmark_gap, "BENCHMARK_GAP_THRESHOLD", 0.03, behind)
    monkeypatch.setattr(rp, "BENCHMARK_GAP_THRESHOLD", 0.02)
    assert "3.0% behind the VWRL.L benchmark" in rp.rule_benchmark_gap(behind)
    ahead = rp.InsightInputs(periods=_periods(ytd_portfolio=0.10, ytd_benchmark=0.07))
    assert "ahead of the benchmark" in rp.rule_benchmark_gap(ahead)
    assert rp.rule_benchmark_gap(rp.InsightInputs(periods=_periods(ytd_portfolio=0.05, ytd_benchmark=0.06))) is None
    missing = [{"period_key": "ytd", "excess_return": None}]
    assert rp.rule_benchmark_gap(rp.InsightInputs(periods=missing)) is None


def test_rule_single_holding_weight(monkeypatch):
    inputs = rp.InsightInputs(weights={"AAA.L": 0.25, "BBB.L": 0.15})
    _assert_boundary(monkeypatch, rp.rule_single_holding_weight, "SINGLE_HOLDING_WEIGHT_THRESHOLD", 0.25, inputs)
    monkeypatch.setattr(rp, "SINGLE_HOLDING_WEIGHT_THRESHOLD", 0.20)
    assert rp.rule_single_holding_weight(inputs).startswith("AAA.L is 25.0%")
    assert rp.rule_single_holding_weight(rp.InsightInputs()) is None


def test_rule_hhi(monkeypatch):
    weights = {"A": 0.4, "B": 0.3, "C": 0.2}  # renormalised over the invested 0.9
    hhi = sum((w / 0.9) ** 2 for w in weights.values())
    inputs = rp.InsightInputs(weights=weights)
    _assert_boundary(monkeypatch, rp.rule_hhi, "HHI_THRESHOLD", hhi, inputs)
    monkeypatch.setattr(rp, "HHI_THRESHOLD", 0.15)
    assert f"HHI {hhi:.2f}" in rp.rule_hhi(inputs)
    assert rp.rule_hhi(rp.InsightInputs(weights={f"T{i}": 0.1 for i in range(10)})) is None


def test_rule_unrecovered_drawdown(monkeypatch):
    risk = [{"key": "current_drawdown", "value": -0.12, "peak_date": "2026-01-30"}]
    inputs = rp.InsightInputs(risk=risk)
    _assert_boundary(monkeypatch, rp.rule_unrecovered_drawdown, "DRAWDOWN_THRESHOLD", 0.12, inputs)
    monkeypatch.setattr(rp, "DRAWDOWN_THRESHOLD", 0.10)
    assert rp.rule_unrecovered_drawdown(inputs) == (
        "The portfolio is 12.0% below its peak of 2026-01-30 and has not yet recovered."
    )
    assert rp.rule_unrecovered_drawdown(rp.InsightInputs()) is None


def test_rule_single_driver(monkeypatch):
    contributors = [
        {"period_key": "month", "ticker": "AAA.L", "contribution_return": 0.012},
        {"period_key": "month", "ticker": "BBB.L", "contribution_return": 0.005},
        {"period_key": "ytd", "ticker": "CCC.L", "contribution_return": 0.5},
    ]
    inputs = rp.InsightInputs(periods=_periods(month=0.02), contributors=contributors)
    share = 0.012 / 0.02
    _assert_boundary(monkeypatch, rp.rule_single_driver, "SINGLE_DRIVER_SHARE_THRESHOLD", share, inputs)
    monkeypatch.setattr(rp, "SINGLE_DRIVER_SHARE_THRESHOLD", 0.6)
    assert rp.rule_single_driver(inputs).startswith("AAA.L drove 60.0% of this month's gain")
    # A month that barely moved is not judged at all.
    quiet = rp.InsightInputs(periods=_periods(month=0.012), contributors=contributors)
    _assert_boundary(monkeypatch, rp.rule_single_driver, "SINGLE_DRIVER_MIN_MOVE", 0.012, quiet)
    losing = rp.InsightInputs(
        periods=_periods(month=-0.02),
        contributors=[{"period_key": "month", "ticker": "ZZZ.L", "contribution_return": -0.015}],
    )
    monkeypatch.setattr(rp, "SINGLE_DRIVER_MIN_MOVE", 0.005)
    assert "this month's loss" in rp.rule_single_driver(losing)


def test_rule_cash_drag(monkeypatch):
    inputs = rp.InsightInputs(cash_weight=0.14)
    _assert_boundary(monkeypatch, rp.rule_cash_drag, "CASH_WEIGHT_THRESHOLD", 0.14, inputs)
    assert rp.rule_cash_drag(rp.InsightInputs()) is None


def test_rule_data_coverage():
    assert rp.rule_data_coverage(rp.InsightInputs()) is None
    assert "No transaction ledger" in rp.rule_data_coverage(rp.InsightInputs(has_ledger=False))
    finding = rp.rule_data_coverage(
        rp.InsightInputs(unreconciled=("BBB.L",), unpriced=("name:SOME FUND", "ref:12", "A", "B", "C", "D"))
    )
    assert "(BBB.L) are excluded" in finding
    assert "Some Fund, unidentified security 12, A, B, C and 1 more" in finding


def test_insight_rows_keep_only_findings_that_fired():
    rows = rp.insight_rows(rp.InsightInputs(cash_weight=0.5))

    assert len(rows) == 1 and rows[0]["finding"].startswith("Cash is 50.0%")


# ──────────────────────────────────────────────────────────────
# Template and rendering
# ──────────────────────────────────────────────────────────────
@pytest.fixture
def benchmark_closes(monkeypatch):
    calls = []

    def load(key, start, end):
        calls.append(key)
        return BENCHMARK

    monkeypatch.setattr(reports.ledger_performance, "load_gbp_closes", load)
    return calls


def test_periodic_summary_is_listed_in_template_metadata():
    metadata = {item["template_id"]: item for item in reports.list_template_metadata()}

    template = metadata["periodic-summary"]
    assert template["name"] == "Periodic summary"
    assert template["builtin"] is True
    assert [section["source"] for section in template["sections"]] == [
        "performance.periods",
        "performance.monthly",
        "performance.risk",
        "performance.contributors",
        "portfolio.insights",
    ]


def test_periodic_summary_renders_demo_data_in_every_format(benchmark_closes):
    document = reports.build_report_document("periodic-summary", "demo-owner", end=END)

    payload = document.to_dict()
    assert payload["parameters"] == {"end": "2026-02-28", "benchmark": "VWRL.L"}
    sections = {section["id"]: section for section in payload["sections"]}
    # The demo owners have holdings but no transaction ledger: portfolio
    # returns are null rather than reconstructed from today's holdings.
    assert all(row["portfolio_return"] is None for row in sections["periods"]["rows"])
    assert sections["periods"]["rows"][1]["benchmark_return"] == pytest.approx(0.0404, abs=1e-6)
    assert sections["risk"]["rows"] == []
    findings = [row["finding"] for row in sections["insights"]["rows"]]
    assert findings[0].startswith("No transaction ledger")
    # The owner's hand-written key findings are merged in after the rules.
    assert findings[1].startswith("US tech concentration")
    assert reports.report_to_csv(document).startswith(b"# Template: Periodic summary")
    assert reports.report_to_pdf(document).startswith(b"%PDF")
    assert benchmark_closes == ["VWRL.L"]


def test_periodic_summary_with_a_ledger(monkeypatch, benchmark_closes):
    monkeypatch.setattr(
        reports.ledger_performance,
        "load_owner_ledgers",
        lambda owner: [lp.AccountLedger("isa", TRANSACTIONS, True)],
    )
    real_build = lp.build_ledger_performance
    monkeypatch.setattr(
        reports.ledger_performance,
        "build_ledger_performance",
        lambda ledgers, end, **kwargs: real_build(
            ledgers, end, holdings=kwargs["holdings"], price_loader=fake_loader()
        ),
    )

    document = reports.build_report_document("periodic-summary", "demo-owner", end=END, benchmark="IWDA.L")

    sections = {section.schema.id: section for section in document.sections}
    assert document.parameters["benchmark"] == "IWDA.L"
    assert sections["periods"].rows[1]["portfolio_return"] == pytest.approx(0.005, abs=1e-6)
    assert sections["monthly"].rows[-1]["cumulative_ytd_return"] == pytest.approx(0.005, abs=1e-6)
    assert sections["contributors"].rows
    findings = [row["finding"] for row in sections["insights"].rows]
    # demo-owner's real holdings are not in this test ledger.
    assert findings[0].startswith("Return history is approximate: holdings the ledger does not reproduce")
    pdf = reports.report_to_pdf(document)
    assert b"Returns by period" in pdf and b"Insights" in pdf
    assert benchmark_closes == ["IWDA.L"]


def test_insights_section_is_omitted_when_nothing_fires(monkeypatch, benchmark_closes):
    monkeypatch.setattr(reports, "_insight_inputs", lambda context: rp.InsightInputs())
    monkeypatch.setattr(reports, "_build_key_findings_section", lambda context, section: [])

    document = reports.build_report_document("periodic-summary", "demo-owner", end=END)

    assert "insights" not in [section.schema.id for section in document.sections]


def test_missing_benchmark_prices_give_null_columns(monkeypatch):
    monkeypatch.setattr(reports.ledger_performance, "load_gbp_closes", lambda *_: pd.Series(dtype=float))

    document = reports.build_report_document("periodic-summary", "demo-owner", end=END)

    periods = next(section for section in document.sections if section.schema.id == "periods")
    assert all(row["benchmark_return"] is None for row in periods.rows)


def test_reporting_end_defaults_to_last_complete_month_end():
    context = reports.ReportContext(owner="demo", start=None, end=None)

    assert context.reporting_end() == lp.last_complete_month_end(date.today())
    assert reports.ReportContext(owner="demo", start=None, end=END).reporting_end() == END


def test_pdf_formats_risk_values_by_units():
    section = reports.ReportSectionData(
        schema=reports.PERIODIC_SUMMARY_TEMPLATE.sections[2],
        rows=(
            {"metric": "Volatility (annualised)", "value": 0.1234, "units": "fraction", "window": "1Y"},
            {"metric": "Sharpe ratio", "value": 0.8765, "units": "number", "window": "1Y"},
        ),
    )
    document = reports.ReportDocument(
        template=reports.PERIODIC_SUMMARY_TEMPLATE,
        owner="demo",
        generated_at=pd.Timestamp("2026-10-01", tz="UTC").to_pydatetime(),
        parameters={},
        sections=(section,),
    )

    pdf = reports.report_to_pdf(document)

    assert b"12.34%" in pdf and b"0.88" in pdf


# ──────────────────────────────────────────────────────────────
# Route
# ──────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(reports_route.router)
    return TestClient(app)


def test_route_passes_benchmark_and_end(client, monkeypatch):
    captured = {}

    def fake_builder(template_id, owner, **kwargs):
        captured.update(kwargs, template_id=template_id)
        return reports.build_report_document(template_id, owner, end=kwargs["end"])

    monkeypatch.setattr(reports_route, "build_report_document", fake_builder)
    monkeypatch.setattr(reports.ledger_performance, "load_gbp_closes", lambda *_: BENCHMARK)

    resp = client.get("/reports/demo-owner/periodic-summary", params={"end": "2026-02-28", "benchmark": " iwda.l "})

    assert resp.status_code == 200
    assert captured["benchmark"] == "IWDA.L"
    assert captured["end"] == END


@pytest.mark.parametrize("benchmark", ["../etc", "A/B", "-X", "X" * 40])
def test_route_rejects_invalid_benchmark(client, benchmark):
    resp = client.get("/reports/demo/periodic-summary", params={"benchmark": benchmark})

    assert resp.status_code == 400


def test_route_unknown_owner_is_404(client, monkeypatch):
    monkeypatch.setattr(reports.ledger_performance, "load_gbp_closes", lambda *_: BENCHMARK)

    resp = client.get("/reports/nobody-here/periodic-summary")

    assert resp.status_code == 404
