"""Retirement readiness monitor: the bot's ``run(owner)`` (#10484).

One run:

1. re-runs the pension forecast through ``/pension/forecast``'s own route
   function (with a stub request, as allotmint-pro's ``get_pension_forecast``
   does) for the current pot, dob, ages and projected pot;
2. converts the projected pot at retirement to today's money at the assumed
   inflation rate and replays it through every historical window of the
   owner's plan mix (:mod:`backend.retirement.drawdown`);
3. compares the result with the previous stored run and attributes the change
   (:mod:`backend.retirement.history`);
4. flags changed assumptions and states current market facts;
5. asks the narrative step (:mod:`backend.retirement.agent`) to describe the
   deterministic results, and stores the run.

Settings not passed in are taken from the previous run, then the defaults
below, so a scheduled run repeats the owner's last choices. Nothing in the
owner's plan, profile or account data is written.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import asdict, dataclass, field, fields
from types import SimpleNamespace
from typing import Any, Mapping, Optional

from backend.common.investment_plan import PlanNotFoundError, load_plan
from backend.common.pension import DEFINED_CONTRIBUTION_ACCOUNT_MARKERS, _age_from_dob, forecast_pension
from backend.logging_setup import sanitise_log_value
from backend.retirement import agent, history
from backend.retirement.drawdown import DrawdownInputs, simulate
from backend.retirement.long_history import LONG_HISTORY_PARTS, LongHistory, LongHistoryError, load_long_history
from backend.retirement.mapping import data_notes, plan_real_returns

logger = logging.getLogger(__name__)

ADVISER_NOTE = (
    "Information only, not advice: this shows historical outcomes and arithmetic. Decisions about "
    "drawdown, withdrawal levels and pension tax should be taken with a regulated financial adviser."
)
NO_STATE_PENSION_NOTE = (
    "No state pension is included: state_pension_annual was not set, so the pot pays the whole income "
    "for life. Set it (e.g. from your gov.uk forecast) to include it from state pension age."
)
CPI_FLAG_THRESHOLD_PP = 1.0
GILT_SERIES = "IUDMNPY"


class ReadinessError(RuntimeError):
    """A run cannot be completed (no plan, no forecast, no long-history data)."""


@dataclass
class ReadinessSettings:
    survival_levels: list[float] = field(default_factory=lambda: [90.0, 95.0, 100.0])
    floor_gbp: Optional[float] = None
    death_age: int = 95
    retirement_age: Optional[int] = None
    state_pension_annual: Optional[float] = None
    contribution_annual: Optional[float] = None
    investment_growth_pct: float = 5.0
    assumed_inflation_pct: float = 2.0

    @classmethod
    def resolve(cls, overrides: Mapping[str, Any], previous: Optional[Mapping[str, Any]]) -> "ReadinessSettings":
        """``overrides`` (non-None values) over the previous run's settings over the defaults."""
        stored = dict((previous or {}).get("settings") or {})
        known = {f.name for f in fields(cls)}
        merged = {k: v for k, v in stored.items() if k in known}
        merged.update({k: v for k, v in overrides.items() if k in known and v is not None})
        settings = cls(**merged)
        if not settings.survival_levels or any(not 0 < p <= 100 for p in settings.survival_levels):
            raise ValueError("survival_levels must be one or more percentages in (0, 100]")
        return settings


def _stub_request() -> Any:
    # resolve_accounts_root only reads (and caches on) request.app.state.
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))


def run_forecast(owner: str, settings: ReadinessSettings, request: Any = None) -> dict:
    """The ``/pension/forecast`` result for these settings (every parameter passed explicitly)."""
    from fastapi import HTTPException

    from backend.routes.pension import pension_forecast

    try:
        return pension_forecast(
            request or _stub_request(),
            owner=owner,
            death_age=settings.death_age,
            state_pension_annual=settings.state_pension_annual,
            db_income_annual=None,
            db_normal_retirement_age=None,
            contribution_annual=settings.contribution_annual,
            contribution_monthly=None,
            investment_growth_pct=settings.investment_growth_pct,
            desired_income_annual=None,
            retirement_age=settings.retirement_age,
        )
    except HTTPException as exc:
        raise ReadinessError(f"pension forecast failed: {exc.detail}") from exc


def build_inputs(forecast: Mapping[str, Any], settings: ReadinessSettings, weights: Mapping[str, float]) -> dict:
    """The run's inputs: everything :func:`evaluate` needs besides the dob and the long history."""
    return {
        "pot_gbp": round(float(forecast["pension_pot_gbp"]), 2),
        "retirement_age": int(forecast["retirement_age"]),
        "death_age": int(settings.death_age),
        "state_pension_age": int(forecast["state_pension_age"]),
        "state_pension_annual": float(settings.state_pension_annual or 0.0),
        "contribution_annual": float(forecast.get("contribution_annual") or 0.0),
        "investment_growth_pct": float(settings.investment_growth_pct),
        "assumed_inflation_pct": float(settings.assumed_inflation_pct),
        "survival_levels": [float(p) for p in settings.survival_levels],
        "floor_gbp": settings.floor_gbp,
        "weights_pct": {k: float(v) for k, v in sorted(weights.items())},
    }


def project_real_pot(inputs: Mapping[str, Any], dob: str, run_date: dt.date) -> dict:
    """Projected pot at retirement (the forecast's own projection) and its value in today's money."""
    projected = forecast_pension(
        dob=dob,
        retirement_age=inputs["retirement_age"],
        death_age=max(inputs["death_age"], inputs["retirement_age"] + 1),
        contribution_annual=inputs["contribution_annual"],
        investment_growth_pct=inputs["investment_growth_pct"],
        initial_pot=inputs["pot_gbp"],
        today=run_date,
        state_pension_age=inputs["state_pension_age"],
    )
    # The forecast compounds from int(current age) to retirement; deflate over the same years.
    current_age = int(_age_from_dob(dob, run_date) or 0)
    years_to_retirement = max(inputs["retirement_age"] - current_age, 0)
    deflator = (1.0 + inputs["assumed_inflation_pct"] / 100.0) ** years_to_retirement
    nominal = float(projected["projected_pot_gbp"])
    return {
        "projected_pot_nominal_gbp": round(nominal, 2),
        "years_to_retirement": years_to_retirement,
        "start_pot_real_gbp": round(nominal / deflator, 2),
    }


def evaluate(inputs: Mapping[str, Any], dob: str, run_date: dt.date, long_history: LongHistory) -> dict:
    """Deterministic results for ``inputs``: projection, plan returns and the drawdown simulation."""
    projection = project_real_pot(inputs, dob, run_date)
    returns = plan_real_returns(inputs["weights_pct"], long_history)
    drawdown_inputs = DrawdownInputs(
        start_pot=projection["start_pot_real_gbp"],
        years=inputs["death_age"] - inputs["retirement_age"],
        state_pension=inputs["state_pension_annual"],
        state_pension_from_year=max(inputs["state_pension_age"] - inputs["retirement_age"], 0),
    )
    simulation = simulate(returns.real_returns, drawdown_inputs, inputs["survival_levels"], inputs["floor_gbp"])
    levels = simulation["sustainable_income"]
    return {
        "projection": projection,
        "simulation": simulation,
        "headline": {
            "survival_pct": inputs["survival_levels"][0],
            "income_gbp": levels[0]["income_gbp"] if levels else None,
        },
        "mapping": {
            "blocks_used": returns.blocks_used,
            "proxy_share_pct": returns.proxy_share_pct,
            "proxies": returns.proxies,
        },
        "data_notes": data_notes(returns),
    }


def _row_date(tx: Any) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(str(tx.date)[:10]) if tx.date else None
    except ValueError:
        return None


_FLOW_SIGNS = {"DEPOSIT": 1.0, "TRANSFER_IN": 1.0, "WITHDRAWAL": -1.0, "TRANSFER_OUT": -1.0}


def pension_flows_between(transactions: list[Any], owner: str, after: dt.date, until: dt.date) -> float:
    """Net GBP paid into the owner's DC pension accounts in ``(after, until]``."""
    total_pence = 0.0
    for tx in transactions:
        sign = _FLOW_SIGNS.get((tx.type or "").strip().upper())
        account = (tx.account or "").lower()
        if sign is None or (tx.owner or "").lower() != owner.lower() or tx.amount_minor is None:
            continue
        if not any(marker in account for marker in DEFINED_CONTRIBUTION_ACCOUNT_MARKERS):
            continue
        day = _row_date(tx)
        if day is not None and after < day <= until:
            total_pence += sign * abs(float(tx.amount_minor))
    return total_pence / 100.0


def _load_transactions() -> list[Any]:
    from backend.routes.transactions import load_all_transactions

    return list(load_all_transactions())


_TRACKED_INPUTS = {
    "retirement_age": "retirement age",
    "death_age": "planning horizon (age)",
    "state_pension_annual": "state pension amount",
    "state_pension_age": "state pension age",
    "weights_pct": "plan target allocation",
    "assumed_inflation_pct": "assumed inflation",
    "investment_growth_pct": "forecast growth assumption",
    "contribution_annual": "annual contribution",
    "survival_levels": "survival levels",
}


def assumption_changes(previous: Optional[Mapping[str, Any]], inputs: Mapping[str, Any]) -> list[dict]:
    """Inputs that changed since the previous run, old and new values side by side."""
    if not previous:
        return []
    before = previous.get("inputs") or {}
    return [
        {"input": key, "label": label, "previous": before.get(key), "current": inputs.get(key)}
        for key, label in _TRACKED_INPUTS.items()
        if key in before and before.get(key) != inputs.get(key)
    ]


def _latest_cpi(long_history: LongHistory) -> Optional[dict]:
    present = [(year, value) for year, value in long_history.cpi.items() if value is not None]
    if not present:
        return None
    year, value = max(present)
    return {"year": year, "pct": round(value * 100.0, 2)}


def _latest_gilt_yield() -> Optional[dict]:
    try:
        from backend.timeseries.boe_rates import load_boe_series

        series = load_boe_series(GILT_SERIES)
    except (ImportError, ValueError, OSError) as exc:
        logger.warning("10-year gilt yield unavailable: %s", sanitise_log_value(exc))
        return None
    if series.empty:
        return None
    last = series.iloc[-1]
    return {"date": last["Date"].date().isoformat(), "pct": round(float(last["Value"]), 2)}


def market_facts(long_history: LongHistory, inputs: Mapping[str, Any]) -> dict:
    """Latest UK CPI and 10-year gilt yield, with a flag when CPI differs from the assumption."""
    cpi = _latest_cpi(long_history)
    flags = []
    if cpi is not None and abs(cpi["pct"] - inputs["assumed_inflation_pct"]) > CPI_FLAG_THRESHOLD_PP:
        flags.append(
            f"UK CPI inflation was {cpi['pct']}% in {cpi['year']}, against the "
            f"{inputs['assumed_inflation_pct']}% assumed when converting the forecast to today's money."
        )
    return {"uk_cpi": cpi, "gilt_10y_yield": _latest_gilt_yield(), "flags": flags}


def caveats(results: Mapping[str, Any], long_history: LongHistory) -> list[str]:
    mapping = results["mapping"]
    proxy_text = "; ".join(f"{p['class']} ({p['weight_pct']}%): {p['proxy']}" for p in mapping["proxies"]) or "none"
    first, last = long_history.years[0], long_history.years[-1]
    return [
        "Past sequences of returns are not a forecast; future returns could be worse than any historical window.",
        f"{mapping['proxy_share_pct']}% of the plan is replayed through proxy series ({proxy_text}).",
        f"Return basis: long-history figures are total returns (income reinvested), {first}-{last}; some daily "
        "price series elsewhere in the app are price-only (#9370).",
        "Fees, charges and taxes are not modelled; returns are gross.",
        "The starting pot is the forecast's projected pot at retirement, converted to today's money at the "
        "assumed inflation rate; incomes are in today's money and rise with inflation.",
        ADVISER_NOTE,
    ]


def digest_items(report: Mapping[str, Any]) -> list[dict]:
    """Short items for a cross-bot digest (#10485)."""
    headline = report["results"]["headline"]
    items = []
    if headline["income_gbp"] is not None:
        items.append(
            {
                "kind": "fact",
                "text": f"Highest real income sustained in {headline['survival_pct']}% of historical windows: "
                f"£{headline['income_gbp']:,.2f} a year.",
            }
        )
    items.extend({"kind": "flag", "text": text} for text in report["market"]["flags"])
    items.extend(
        {"kind": "flag", "text": f"Changed since the last run: {change['label']}."}
        for change in report["assumption_changes"]
    )
    return items


def _plan_weights(owner: str, request: Any) -> dict[str, float]:
    from backend.routes._accounts import resolve_accounts_root

    accounts_root = resolve_accounts_root(request or _stub_request())
    try:
        return load_plan(owner, accounts_root.parent).target_weights()
    except PlanNotFoundError as exc:
        raise ReadinessError(f"no investment plan saved for {owner}; the simulation replays the plan mix") from exc
    except ValueError as exc:
        raise ReadinessError(f"saved investment plan for {owner} is invalid: {exc}") from exc


def _attribution(
    previous: Optional[Mapping[str, Any]], inputs: dict, results: dict, owner: str, context: dict
) -> Optional[dict]:
    income = results["headline"]["income_gbp"]
    if not previous or income is None or previous.get("headline", {}).get("income_gbp") is None:
        return None
    after = dt.date.fromisoformat(str(previous["run_date"]))

    # Counterfactuals keep the previous run's date, so the passing of time counts as an assumption change.
    def compute(candidate: Mapping[str, Any]) -> float:
        value = evaluate(candidate, context["dob"], after, context["long_history"])["headline"]["income_gbp"]
        return float(value or 0.0)

    flows = pension_flows_between(context["load_transactions"](), owner, after, context["run_date"])
    return history.attribute_change(previous, inputs, float(income), flows, compute)


#: The parts of the ``/pension/forecast`` result kept in the report.
_FORECAST_KEYS = ("pension_pot_gbp", "projected_pot_gbp", "current_age", "retirement_age", "state_pension_age")


def run(
    owner: str,
    *,
    overrides: Optional[Mapping[str, Any]] = None,
    request: Any = None,
    today: Optional[dt.date] = None,
    long_history: Optional[LongHistory] = None,
    narrative_llm: Optional[agent.NarrativeLLM] = None,
    load_transactions: Any = None,
    save: bool = True,
) -> dict:
    """Run the monitor for ``owner`` and (by default) store the report; returns the report."""
    run_date = today or dt.date.today()
    previous = history.previous_run(owner, run_date.isoformat())
    settings = ReadinessSettings.resolve(overrides or {}, previous)
    try:
        long_history = long_history or load_long_history()
    except LongHistoryError as exc:
        raise ReadinessError(str(exc)) from exc
    forecast = run_forecast(owner, settings, request)
    inputs = build_inputs(forecast, settings, _plan_weights(owner, request))
    dob = str(forecast["dob"])
    context = {
        "dob": dob,
        "run_date": run_date,
        "long_history": long_history,
        "load_transactions": load_transactions or _load_transactions,
    }
    results = evaluate(inputs, dob, run_date, long_history)
    if not inputs["state_pension_annual"]:
        results["data_notes"].append(NO_STATE_PENSION_NOTE)
    if abs(results["projection"]["projected_pot_nominal_gbp"] - float(forecast["projected_pot_gbp"])) > 1.0:
        results["data_notes"].append("The forecast's projected pot differs from the one simulated; check the run date.")
    report: dict[str, Any] = {
        "owner": owner,
        "run_date": run_date.isoformat(),
        "settings": asdict(settings),
        "inputs": inputs,
        "forecast": {key: forecast.get(key) for key in _FORECAST_KEYS},
        "headline": results["headline"],
        "results": results,
        "attribution": _attribution(previous, inputs, results, owner, context),
        "assumption_changes": assumption_changes(previous, inputs),
        "market": market_facts(long_history, inputs),
        "caveats": caveats(results, long_history),
        "data_source": {
            "long_history": "/".join(LONG_HISTORY_PARTS),
            "years": [long_history.years[0], long_history.years[-1]] if long_history.years else [],
            "basis": long_history.basis,
        },
    }
    report["digest_items"] = digest_items(report)
    report["narrative"] = agent.write_narrative(report, llm=narrative_llm)
    report["storage"] = _store(owner, report) if save else {"stored": False, "reason": "not requested"}
    return report


def _store(owner: str, report: Mapping[str, Any]) -> dict:
    """Save the report; a storage failure is logged and reported, not raised, so the run's result is kept."""
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        history.save_run(owner, report)
    except (OSError, ValueError, ClientError, BotoCoreError) as exc:  # ValueError: a malformed store URI
        # The detail stays in the server log; the response carries a fixed message.
        logger.warning("Retirement readiness report not stored: %s", sanitise_log_value(exc))
        return {"stored": False, "reason": "The report could not be stored; see the server log."}
    return {"stored": True, "reason": None}


__all__ = ["ReadinessError", "ReadinessSettings", "evaluate", "run"]
