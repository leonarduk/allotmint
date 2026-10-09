"""Guardian report guardrails (#10479): no advice wording, the not-modelled list always shown."""

from __future__ import annotations

import ast
import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.allowance_guardian as guardian
from backend.allowance_guardian import report
from backend.allowance_guardian.schedule import ContributionSchedule, ScheduledContribution, save_schedule
from backend.routes.transactions import Transaction

TODAY = date(2026, 10, 9)

# Imperative or recommending wording the report must never contain.
ADVICE_PATTERNS = [
    r"\byou should\b",
    r"\bshould (?:you )?(?:contribute|pay|use|increase|reduce|consider)\b",
    r"\b(?:we )?recommend",
    r"\bconsider (?:using|paying|contributing|increasing|reducing)\b",
    r"\buse (?:your )?carry[- ]forward\b",
    r"\bcontribute (?:£|up to|more|less|another)",
    r"\b(?:increase|reduce|top up|stop|pause) your\b",
    r"\bbest to\b",
    r"\bmake sure\b",
]


def advice_phrases(text: str) -> list[str]:
    return [p for p in ADVICE_PATTERNS if re.search(p, text, flags=re.IGNORECASE)]


def _fake_allowances(view: dict) -> SimpleNamespace:
    return SimpleNamespace(
        carry_forward_view=lambda transactions, today: view,
        annual_allowance_info=lambda account, tax_year: {"limit_gbp": 20_000.0, "assumed": False},
    )


def _breach_view() -> dict:
    earlier = [
        {"tax_year": y, "annual_allowance_gbp": 60_000.0, "unused_allowance_gbp": 0.0, "is_current_tax_year": False}
        for y in ("2023-2024", "2024-2025", "2025-2026")
    ]
    current = {
        "tax_year": "2026-2027",
        "annual_allowance_gbp": 60_000.0,
        "gross_contributions_gbp": 55_000.0,
        "employer_contributions_gbp": 55_000.0,
        "excess_not_covered_by_carry_forward_gbp": 0.0,
        "is_current_tax_year": True,
    }
    return {"tax_years": [*earlier, current], "current_year_allowance_remaining_gbp": 5_000.0}


def _schedule() -> list[ScheduledContribution]:
    return [
        ScheduledContribution(
            account="sipp", amount_minor=1_000_000, source="employer", expected_day=28, start_date="2026-04-28"
        ),
        ScheduledContribution(
            account="isa", amount_minor=500_000, source="isa_subscription", expected_day=1, start_date="2026-11-01"
        ),
    ]


def _report(**kwargs) -> dict:
    allowances = _fake_allowances(_breach_view())
    defaults = {"today": TODAY, "transactions": [], "schedule": _schedule(), "allowances": allowances}
    return guardian.run("alex", **{**defaults, **kwargs})


def test_advice_checker_catches_imperative_wording():
    for bad in (
        "You should use carry-forward from 2023-24.",
        "Consider increasing your contributions.",
        "Contribute £5,000 more before April.",
        "We recommend pausing payments.",
        "Use your carry-forward allowance.",
    ):
        assert advice_phrases(bad), bad


@pytest.mark.parametrize("allowances", ["fake", None])
def test_report_has_no_advice_wording(allowances):
    result = _report(allowances=_fake_allowances(_breach_view()) if allowances else None)
    found = advice_phrases(json.dumps(result, ensure_ascii=False))
    assert not found, found


def test_guardian_source_has_no_advice_wording():
    """Covers every string literal in the package, including messages a test fixture doesn't reach."""
    package = Path(guardian.__file__).parent
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not advice_phrases(node.value), (path.name, node.value)


@pytest.mark.parametrize("allowances", ["fake", None])
def test_every_report_lists_what_is_not_modelled_and_the_adviser_note(allowances):
    result = _report(allowances=_fake_allowances(_breach_view()) if allowances else None)
    text = " ".join(result["not_modelled"]).lower()
    assert "tapered annual allowance" in text
    assert "money purchase annual allowance" in text
    assert "not recorded in allotmint" in text
    assert "regulated financial adviser" in result["adviser_note"]
    assert "not advice" in result["adviser_note"]


def test_breach_and_isa_alerts_are_raised():
    result = _report()
    codes = {alert["code"] for alert in result["alerts"]}
    # 5,000 left; 10,000 a month from 28 Oct and no carry-forward: over in October.
    assert result["pension_allowance"]["projected_breach"]["month"] == "2026-10"
    assert "pension_projected_breach" in codes
    # No ISA subscriptions recorded; 1 Nov .. 1 Apr = 6 x 5,000 = 30,000 > the 20,000 limit.
    assert "isa_over_limit" in codes
    # 28 Apr .. 28 Aug expected, none recorded, windows closed; 28 Sep is still awaited.
    assert result["contributions"]["counts"]["missing"] == 5
    assert "contribution_missing" in codes


def test_without_allotmint_pro_allowance_sections_say_so():
    result = _report(allowances=None)
    assert result["pension_allowance"] == {"available": False, "reason": report.UPGRADE_MESSAGE}
    assert result["isa_allowance"]["available"] is False
    assert result["contributions"]["counts"]["missing"] == 5


def test_tax_year_and_as_of_use_the_london_date(monkeypatch):
    # 23:30 UTC on 5 April 2027 is 00:30 on 6 April in London (BST): the new tax year.
    class _Clock:
        @staticmethod
        def now(tz):
            from datetime import datetime, timezone

            return datetime(2027, 4, 5, 23, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(report, "datetime", _Clock)
    result = guardian.run("alex", transactions=[], schedule=[], allowances=None)
    assert result["as_of"] == "2027-04-06"
    assert result["tax_year"] == "2027-2028"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_run_is_read_only(monkeypatch, tmp_path):
    """The guardian loads the stored schedule and writes nothing (only the owner's PUT saves)."""
    save_schedule(ContributionSchedule(owner="alex", contributions=_schedule()), tmp_path)
    before = _snapshot(tmp_path)

    def _forbidden(*args, **kwargs):
        raise AssertionError("guardian must not write")

    monkeypatch.setattr("backend.allowance_guardian.schedule.save_schedule", _forbidden)
    rows = [Transaction(owner="alex", account="sipp", type="DEPOSIT", date="2026-09-28", amount_minor=1_000_000,
                        comments="Employer contribution")]  # fmt: skip
    result = _report(transactions=rows, schedule=None, data_root=tmp_path)
    assert result["schedule_count"] == 2
    assert result["contributions"]["counts"]["on_time"] == 1
    assert _snapshot(tmp_path) == before
