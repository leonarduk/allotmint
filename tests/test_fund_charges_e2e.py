"""End-to-end: a fund's catalogue ``ongoing_charge_pct`` reaches built portfolios (#7834).

``enrich_holding`` reads the charge from ``meta`` after merging the instrument
catalogue (``get_instrument_meta``) over the portfolio-derived security meta
(``backend/common/holding_utils.py`` ``enrich_holding``: ``meta =
get_instrument_meta(full)`` then ``meta = {**sec_meta, **instr_meta}``). These
tests use the *real* ``get_instrument_meta`` against a temporary instruments
directory -- nothing in the metadata path is monkeypatched -- so they fail if
the charge were read from portfolio-derived meta only.
"""

import json
from datetime import date

import pytest

from backend.common import group_portfolio, holding_utils, instruments, portfolio_utils
from backend.common import portfolio as owner_portfolio
from backend.common.account_models import OwnerSummaryRecord
from backend.common.constants import ACCOUNTS, HOLDINGS
from backend.common.holding_utils import enrich_holding
from backend.config import config
from backend.timeseries.cache import cache_only

FUND = "VWRL.L"
NO_FEE = "NOFEE.L"


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    """A temporary instruments catalogue: one fund with a charge, one without."""
    inst_dir = tmp_path / "instruments"
    (inst_dir / "L").mkdir(parents=True)
    (inst_dir / "L" / "VWRL.json").write_text(
        json.dumps({"ticker": FUND, "name": "All-World Fund", "currency": "GBP", "ongoing_charge_pct": 0.22})
    )
    (inst_dir / "L" / "NOFEE.json").write_text(json.dumps({"ticker": NO_FEE, "name": "No Fee Data", "currency": "GBP"}))
    monkeypatch.delenv(instruments.METADATA_BUCKET_ENV, raising=False)
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", inst_dir)
    # ``get_instrument_meta`` is ``lru_cache``d, and other tests
    # ``importlib.reload(backend.common.instruments)`` -- leaving the modules
    # that did ``from ... import get_instrument_meta`` holding the *pre-reload*
    # function, whose cache no ``instruments.get_instrument_meta.cache_clear()``
    # reaches and may already hold a "VWRL.L" entry read from the real data
    # root. Bind those modules to the current function (still the real,
    # unpatched lookup) and start and finish with an empty cache.
    monkeypatch.setattr(holding_utils, "get_instrument_meta", instruments.get_instrument_meta)
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", instruments.get_instrument_meta)
    instruments.get_instrument_meta.cache_clear()
    yield inst_dir
    instruments.get_instrument_meta.cache_clear()


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    """An owner ``steve`` with one ISA holding both instruments."""
    root = tmp_path / "accounts"
    owner_dir = root / "steve"
    owner_dir.mkdir(parents=True)
    account = {
        "owner": "steve",
        "account_type": "ISA",
        "currency": "GBP",
        HOLDINGS: [
            {"ticker": FUND, "units": 10.0, "cost_basis_gbp": 1000.0},
            {"ticker": NO_FEE, "units": 5.0, "cost_basis_gbp": 500.0},
        ],
    }
    (owner_dir / "isa.json").write_text(json.dumps(account))
    monkeypatch.setattr(config, "accounts_root", root)
    return root


def _by_ticker(holdings):
    return {h["ticker"]: h for h in holdings}


def test_real_catalogue_lookup_returns_the_charge(catalogue):
    assert instruments.get_instrument_meta(FUND)["ongoing_charge_pct"] == 0.22


def test_enrich_holding_reads_charge_from_real_catalogue(catalogue, monkeypatch):
    # Portfolio-derived security meta never carries the charge; the catalogue
    # entry must still win when the two are merged.
    monkeypatch.setattr(
        "backend.common.portfolio_utils.get_security_meta",
        lambda _t: {"name": "From portfolio", "currency": "GBP"},
    )
    with cache_only():  # as the portfolio builders call it: no live price fetch
        known = enrich_holding({"ticker": FUND, "units": 10.0}, date.today(), {}, {})
        unknown = enrich_holding({"ticker": NO_FEE, "units": 5.0}, date.today(), {}, {})
    assert known["ongoing_charge_pct"] == 0.22
    assert unknown["ongoing_charge_pct"] is None


def test_owner_portfolio_holdings_carry_the_charge(catalogue, accounts, monkeypatch):
    plots = [OwnerSummaryRecord(owner="steve", accounts=["isa"])]
    monkeypatch.setattr(owner_portfolio, "list_plots", lambda *_a, **_k: plots)

    pf = owner_portfolio.build_owner_portfolio("steve", accounts)

    holdings = _by_ticker(pf[ACCOUNTS][0][HOLDINGS])
    assert holdings[FUND]["ongoing_charge_pct"] == 0.22
    assert holdings[NO_FEE]["ongoing_charge_pct"] is None


def test_group_portfolio_holdings_carry_the_charge(catalogue, accounts, monkeypatch):
    portfolio = {
        "owner": "steve",
        ACCOUNTS: [
            {
                "account_type": "ISA",
                "currency": "GBP",
                HOLDINGS: [
                    {"ticker": FUND, "units": 10.0, "cost_basis_gbp": 1000.0},
                    {"ticker": NO_FEE, "units": 5.0, "cost_basis_gbp": 500.0},
                ],
            }
        ],
    }
    plots = [OwnerSummaryRecord(owner="steve", accounts=["isa"])]
    monkeypatch.setattr("backend.common.portfolio_loader.list_portfolios", lambda *_a, **_k: [portfolio])
    monkeypatch.setattr(group_portfolio.data_loader, "list_plots", lambda *_a, **_k: plots)
    monkeypatch.setattr(group_portfolio, "load_approvals", lambda *_a, **_k: {})
    monkeypatch.setattr(group_portfolio, "load_user_config", lambda *_a, **_k: None)
    monkeypatch.setattr(group_portfolio.owner_portfolio, "build_owner_portfolio", lambda *_a, **_k: {})

    pf = group_portfolio.build_group_portfolio("all")

    holdings = _by_ticker(h for acct in pf[ACCOUNTS] for h in acct[HOLDINGS])
    assert holdings[FUND]["ongoing_charge_pct"] == 0.22
    assert holdings[NO_FEE]["ongoing_charge_pct"] is None
