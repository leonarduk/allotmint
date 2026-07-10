"""Lambda entry point to generate and email a pension performance report on a schedule.

See ``backend.common.pension`` for the forecast/shortfall/YTD calculations and
``backend.emails.pension_report`` for the SES/Jinja2 send pattern (mirrors
``backend.emails.weekly_report``, issue #2758).

Recipient selection
--------------------
The owners to report on are read from an SSM-backed (or local-file, in dev)
JSON blob via ``backend.common.storage.get_storage`` -- the same
env-var-configurable pattern already used by ``backend.alerts``,
``backend.common.goals``, ``backend.nudges`` and ``backend.quests``. Each
owner's email is taken from their existing person metadata rather than
duplicating it in the recipient config. If no recipient config is present,
every owner discovered by ``list_portfolios()`` is reported on.

Failure handling
-----------------
Per-owner failures are caught and logged so one broken portfolio does not stop
the report for everyone else. A failure notification is published via
``backend.common.alerts.publish_sns_alert`` (not a silent failure) whenever
initialisation fails outright or any owner's report could not be generated.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from backend.common.alerts import publish_sns_alert
from backend.common.pension import (
    _age_from_dob,
    dc_pension_pot_gbp,
    forecast_pension,
    pension_shortfall_vs_target,
    pension_ytd_return,
    state_pension_age_uk,
)
from backend.common.pension_snapshots import (
    get_previous_snapshot,
    previous_period_pot_gbp,
    record_snapshot,
    ytd_baseline_pot_gbp,
)
from backend.common.portfolio_loader import list_portfolios
from backend.common.storage import get_storage
from backend.emails.pension_report import PensionReport, send_pension_report_email

logger = logging.getLogger("pension_report")

_DEFAULT_RECIPIENTS_URI = "ssm://pension-report-recipients"

# (display label, env var, default growth %)
_GROWTH_SCENARIOS: Tuple[Tuple[str, str, str], ...] = (
    ("Pessimistic", "PENSION_REPORT_GROWTH_PESSIMISTIC_PCT", "2.0"),
    ("Base", "PENSION_REPORT_GROWTH_BASE_PCT", "5.0"),
    ("Optimistic", "PENSION_REPORT_GROWTH_OPTIMISTIC_PCT", "8.0"),
)


def _death_age() -> int:
    return int(os.getenv("PENSION_REPORT_DEATH_AGE", "95"))


def _desired_income_annual() -> Optional[float]:
    value = os.getenv("PENSION_REPORT_DESIRED_INCOME_ANNUAL")
    return float(value) if value else None


def _contribution_annual() -> float:
    return float(os.getenv("PENSION_REPORT_CONTRIBUTION_ANNUAL", "0"))


def _drawdown_alert_pct() -> float:
    return float(os.getenv("PENSION_REPORT_DRAWDOWN_ALERT_PCT", "10.0"))


def _load_recipient_owners() -> Optional[List[str]]:
    """Return the configured list of owners to report on, or ``None`` for "all owners"."""

    uri = os.getenv("PENSION_REPORT_RECIPIENTS_URI", _DEFAULT_RECIPIENTS_URI)
    data = get_storage(uri).load()
    owners = data.get("owners")
    if not owners:
        return None
    return [str(owner) for owner in owners]


def _build_report_for_owner(
    owner: str,
    person: Dict[str, Any],
    accounts: List[Dict[str, Any]],
    today: dt.date,
) -> Optional[Tuple[PensionReport, str]]:
    dob = person.get("dob")
    email = person.get("email")
    if not dob or not email:
        logger.warning("Skipping pension report for %s: missing dob or email", owner)
        return None

    current_age = _age_from_dob(dob, today)
    if current_age is None:
        logger.warning("Skipping pension report for %s: invalid dob", owner)
        return None

    retirement_age = state_pension_age_uk(dob)
    # Keep the forecast beyond retirement even for a minimal configured death
    # age, mirroring backend.routes.pension's forecast_death_age safeguard --
    # forecast_pension() only populates projected_pot_gbp at retirement_age.
    death_age = max(_death_age(), retirement_age + 1)
    pot_gbp = dc_pension_pot_gbp(accounts)
    contribution_annual = _contribution_annual()
    desired_income_annual = _desired_income_annual()

    previous = get_previous_snapshot(owner)
    start_of_year_pot = ytd_baseline_pot_gbp(previous, pot_gbp, today)
    previous_period_pot = previous_period_pot_gbp(previous, pot_gbp)
    ytd = pension_ytd_return(
        current_pot_gbp=pot_gbp,
        pot_start_of_year_gbp=start_of_year_pot,
        contributions_ytd_gbp=0.0,
    )

    ytd_change = f"£{ytd['ytd_gain_gbp']:,.2f}"
    if ytd["ytd_return_pct"] is not None:
        ytd_change += f" ({ytd['ytd_return_pct']:.1f}%)"
    stats = {
        "Current pot value": f"£{pot_gbp:,.2f}",
        "YTD change": ytd_change,
    }

    scenarios: List[Dict[str, str]] = []
    base_forecast: Optional[Dict[str, Any]] = None
    for label, env_var, default in _GROWTH_SCENARIOS:
        growth_pct = float(os.getenv(env_var, default))
        forecast = forecast_pension(
            dob=dob,
            retirement_age=retirement_age,
            death_age=death_age,
            contribution_annual=contribution_annual,
            investment_growth_pct=growth_pct,
            desired_income_annual=desired_income_annual,
            initial_pot=pot_gbp,
            today=today,
        )
        if label == "Base":
            base_forecast = forecast
        scenarios.append(
            {
                "label": f"{label} ({growth_pct:.1f}% growth)",
                "projected_pot_gbp": f"£{forecast['projected_pot_gbp']:,.2f}",
            }
        )

    alerts: List[str] = []
    if desired_income_annual is not None and base_forecast is not None:
        shortfall = pension_shortfall_vs_target(
            projected_pot_gbp=base_forecast["projected_pot_gbp"],
            desired_income_annual=desired_income_annual,
        )
        if not shortfall["on_track"]:
            alerts.append(
                f"Projected pot is £{shortfall['shortfall_gbp']:,.2f} short of the "
                f"target needed to support £{desired_income_annual:,.2f}/yr in retirement."
            )

    if previous_period_pot:
        drawdown_pct = (pot_gbp - previous_period_pot) / previous_period_pot * 100.0
        if drawdown_pct <= -_drawdown_alert_pct():
            alerts.append(
                f"Pot value dropped {abs(drawdown_pct):.1f}% since the last report "
                f"(£{previous_period_pot:,.2f} -> £{pot_gbp:,.2f})."
            )

    record_snapshot(owner, pot_gbp=pot_gbp, as_of=today)

    report = PensionReport(
        owner_name=str(person.get("full_name") or owner),
        stats=stats,
        scenarios=scenarios,
        alerts=alerts,
    )
    return report, email


def lambda_handler(event, context):
    """Lambda handler invoked by the scheduled EventBridge rule."""

    today = dt.date.today()

    try:
        target_owners = _load_recipient_owners()
        portfolios = list_portfolios()
    except Exception as exc:
        logger.error("Pension report failed to initialise: %s", exc, exc_info=True)
        publish_sns_alert(
            {
                "message": f"Pension report Lambda failed to start: {exc}",
                "ticker": "pension-report",
            }
        )
        return {"sent": 0, "errors": [str(exc)]}

    sent = 0
    errors: List[str] = []
    for portfolio in portfolios:
        owner = portfolio["owner"]
        if target_owners is not None and owner not in target_owners:
            continue
        try:
            built = _build_report_for_owner(
                owner, portfolio.get("person") or {}, portfolio.get("accounts") or [], today
            )
            if built is None:
                continue
            report, email = built
            send_pension_report_email(email, report)
            sent += 1
        except Exception as exc:
            logger.error("Pension report failed for owner %s: %s", owner, exc, exc_info=True)
            errors.append(f"{owner}: {exc}")

    if errors:
        publish_sns_alert(
            {
                "message": f"Pension report failed for {len(errors)} owner(s): {'; '.join(errors)}",
                "ticker": "pension-report",
            }
        )

    return {"sent": sent, "errors": errors}
