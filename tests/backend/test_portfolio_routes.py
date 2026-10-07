import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import portfolio


def _client(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(portfolio.router)
    app.state.accounts_root = tmp_path
    return TestClient(app)


def test_portfolio_success(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: {"owner": owner},
    )
    resp = client.get("/portfolio/alice")
    assert resp.status_code == 200
    assert resp.json()["owner"] == "alice"


def test_portfolio_not_found(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: (_ for _ in ()).throw(FileNotFoundError()),
    )
    resp = client.get("/portfolio/bob")
    assert resp.status_code == 404


def test_portfolio_sectors(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    sample_portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "AAA",
                        "sector": "Tech",
                        "market_value_gbp": 150,
                        "cost_gbp": 100,
                        "gain_gbp": 50,
                    },
                    {
                        "ticker": "BBB",
                        "sector": "Finance",
                        "market_value_gbp": 220,
                        "cost_gbp": 200,
                        "gain_gbp": 20,
                    },
                ]
            }
        ],
    }

    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: sample_portfolio,
    )

    resp = client.get("/portfolio/alice/sectors")
    assert resp.status_code == 200
    sectors = {row["sector"]: row for row in resp.json()}
    assert sectors["Tech"]["market_value_gbp"] == 150
    assert sectors["Finance"]["gain_gbp"] == 20


def _currency_portfolio():
    return {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "QXA.L", "currency": "GBP", "market_value_gbp": 100, "cost_gbp": 90, "gain_gbp": 10},
                    {"ticker": "QXB.L", "currency": "GBX", "market_value_gbp": 50, "cost_gbp": 40, "gain_gbp": 10},
                    {"ticker": "QXC.N", "currency": "USD", "market_value_gbp": 250, "cost_gbp": 200, "gain_gbp": 50},
                ]
            }
        ],
    }


@pytest.fixture
def _offline_currency_meta(monkeypatch):
    from backend.common import instrument_api

    monkeypatch.setattr("backend.common.portfolio_utils.get_instrument_meta", lambda ticker: {})
    monkeypatch.setattr("backend.common.portfolio_utils.get_security_meta", lambda ticker: {})
    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda ticker, snapshot: (ticker, None))


@pytest.mark.usefixtures("_offline_currency_meta")
def test_portfolio_currencies(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: _currency_portfolio(),
    )

    resp = client.get("/portfolio/alice/currencies")
    assert resp.status_code == 200
    groups = {row["quote_currency"]: row for row in resp.json()}
    assert set(groups) == {"GBP", "USD"}
    assert groups["GBP"]["market_value_gbp"] == 150
    assert groups["USD"]["market_value_gbp"] == 250
    assert groups["GBP"]["unconverted_holdings"] == []
    assert isinstance(groups["USD"]["unconverted_holdings"], list)
    assert sum(g["weight_pct"] for g in groups.values()) == pytest.approx(100.0)


@pytest.mark.usefixtures("_offline_currency_meta")
def test_portfolio_currencies_flags_unpriced_missing_fx_holding(monkeypatch, tmp_path):
    """An enriched holding with no FX rate (#9664: unpriced, fx_rate_source "missing") is flagged, not valued."""
    from backend.common import portfolio_utils
    from backend.utils.fx_rates import FX_RATE_SOURCE_MISSING

    monkeypatch.setattr(portfolio_utils, "cached_fx_rate_to_gbp", lambda ccy: {"JPY": 0.0052}.get(ccy))
    holdings = [
        {"ticker": "QXA.L", "currency": "GBP", "market_value_gbp": 100, "cost_gbp": 90, "gain_gbp": 10},
        {
            "ticker": "QXT.JP",
            "currency": "JPY",
            "fx_rate_source": FX_RATE_SOURCE_MISSING,
            "market_value_gbp": None,
            "cost_gbp": 30,
            "gain_gbp": None,
        },
    ]
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: {"accounts": [{"holdings": holdings}]},
    )

    resp = client.get("/portfolio/alice/currencies")
    assert resp.status_code == 200
    groups = {row["quote_currency"]: row for row in resp.json()}
    assert groups["JPY"]["market_value_gbp"] == 0
    assert groups["JPY"]["unconverted_holdings"] == [
        {"ticker": "QXT.JP", "currency": "JPY", "reason": portfolio_utils.FX_MISSING_ALL_DATES}
    ]
    assert groups["GBP"]["weight_pct"] == pytest.approx(100.0)


def test_portfolio_currencies_not_found(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: (_ for _ in ()).throw(FileNotFoundError()),
    )
    resp = client.get("/portfolio/bob/currencies")
    assert resp.status_code == 404


@pytest.mark.parametrize("path", ["/portfolio/alice/currencies", "/portfolio-group/all/currencies"])
def test_currency_routes_aggregate_cache_only(monkeypatch, tmp_path, path):
    """Page requests must read cached prices and FX only, never Yahoo (#8028)."""
    from backend.timeseries.cache import is_cache_only

    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: {"accounts": []},
    )
    monkeypatch.setattr(
        "backend.routes.portfolio.group_portfolio.build_group_portfolio",
        lambda slug, **_kwargs: {"slug": slug, "accounts": []},
    )
    seen = []
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_utils.aggregate_by_currency",
        lambda data: seen.append(is_cache_only()) or [],
    )

    assert client.get(path).status_code == 200
    assert seen == [True]


@pytest.mark.usefixtures("_offline_currency_meta")
def test_group_currencies(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.group_portfolio.build_group_portfolio",
        lambda slug, **_kwargs: {"slug": slug, **_currency_portfolio()},
    )

    resp = client.get("/portfolio-group/all/currencies")
    assert resp.status_code == 200
    groups = {row["quote_currency"]: row for row in resp.json()}
    assert set(groups) == {"GBP", "USD"}
    assert groups["GBP"]["currency"] == "GBP"


def test_group_currencies_not_found(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    def _missing(slug, **_kwargs):
        raise ValueError(slug)

    monkeypatch.setattr("backend.routes.portfolio.group_portfolio.build_group_portfolio", _missing)
    resp = client.get("/portfolio-group/nope/currencies")
    assert resp.status_code == 404


@pytest.mark.parametrize("path", ["/portfolio/alice/look-through", "/portfolio-group/all/look-through"])
def test_look_through_routes_compute_cache_only(monkeypatch, tmp_path, path):
    """Look-through (#9974) reads stored metadata and cached prices only (#8028)."""
    from backend.timeseries.cache import is_cache_only

    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: {"owner": owner, "accounts": []},
    )
    monkeypatch.setattr(
        "backend.routes.portfolio.group_portfolio.build_group_portfolio",
        lambda slug, **_kwargs: {"slug": slug, "accounts": []},
    )
    seen = []
    monkeypatch.setattr(
        "backend.routes.portfolio.look_through.compute_look_through",
        lambda data: seen.append(is_cache_only()) or {"total_value_gbp": 0.0},
    )

    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.json() == {"total_value_gbp": 0.0}
    assert seen == [True]


def test_look_through_routes_not_found(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.portfolio_mod.build_owner_portfolio",
        lambda owner, root, pricing_date=None: (_ for _ in ()).throw(FileNotFoundError()),
    )

    def _missing(slug, **_kwargs):
        raise ValueError(slug)

    monkeypatch.setattr("backend.routes.portfolio.group_portfolio.build_group_portfolio", _missing)
    assert client.get("/portfolio/bob/look-through").status_code == 404
    assert client.get("/portfolio-group/nope/look-through").status_code == 404


def test_portfolio_var(monkeypatch, tmp_path):
    pytest.importorskip("allotmint_pro")
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.risk.compute_portfolio_var",
        lambda owner, days, confidence, include_cash: {"1d": 1.0},
    )
    monkeypatch.setattr(
        "backend.routes.portfolio.risk.compute_sharpe_ratio",
        lambda owner, days: 0.5,
    )
    resp = client.get("/var/alice", params={"days": 10, "confidence": 0.9})
    assert resp.status_code == 200
    data = resp.json()
    assert data["var"] == {"1d": 1.0}
    assert data["sharpe_ratio"] == 0.5


def test_portfolio_var_owner_missing(monkeypatch, tmp_path):
    pytest.importorskip("allotmint_pro")
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "backend.routes.portfolio.risk.compute_portfolio_var",
        lambda owner, days=365, confidence=0.95, include_cash=True: (_ for _ in ()).throw(FileNotFoundError()),
    )
    resp = client.get("/var/alice")
    assert resp.status_code == 404


def test_portfolio_var_bad_params(monkeypatch, tmp_path):
    pytest.importorskip("allotmint_pro")
    client = _client(monkeypatch, tmp_path)

    def _raise(owner, days, confidence, include_cash):
        raise ValueError("bad")

    monkeypatch.setattr("backend.routes.portfolio.risk.compute_portfolio_var", _raise)
    resp = client.get("/var/alice")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Path traversal — /account/{owner}/{account}
# ---------------------------------------------------------------------------


def test_account_percent_encoded_slash_owner_returns_404(monkeypatch, tmp_path):
    """A %2F-encoded slash in the owner segment returns 404.

    When '%2F' is decoded by the HTTP layer the path becomes
    '/account/../evil/isa', which routers normalise to '/account/evil/isa'.
    This returns 404 because no such owner exists — the traversal is blocked
    at the URL-normalisation layer, *before* safe_join is reached.

    The safe_join guard for a decoded '../evil' owner is verified directly in
    tests/backend/routes/test_accounts_helpers.py::
        test_resolve_owner_directory_dotdot_returns_none
    and in tests/backend/common/test_data_loader.py::
        test_load_account_dotdot_owner_raises_missing_data.
    """
    client = _client(monkeypatch, tmp_path)
    resp = client.get("/account/..%2Fevil/isa")
    assert resp.status_code == 404


def test_account_case_insensitive_owner_and_account_loads_matched_directory(monkeypatch, tmp_path):
    """Owner/account casing mismatches should load the on-disk match."""
    owner_dir = tmp_path / "Alice"
    owner_dir.mkdir()
    (owner_dir / "isa.json").write_text(
        json.dumps({"account_type": "ISA", "holdings": [{"ticker": "ABC"}]}),
        encoding="utf-8",
    )
    client = _client(monkeypatch, tmp_path)

    resp = client.get("/account/alice/ISA")

    assert resp.status_code == 200
    assert resp.json()["account_type"] == "ISA"
    assert resp.json()["holdings"] == [{"ticker": "ABC"}]


def test_account_valid_missing_returns_404(monkeypatch, tmp_path):
    """Non-existent but valid owner/account yields 404, not 500."""
    client = _client(monkeypatch, tmp_path)
    resp = client.get("/account/noowner/noaccount")
    assert resp.status_code == 404
