"""A corrupt data file is reported as such, not as a missing group (#11428)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app as app_module
from backend.app import create_app
from backend.common import group_portfolio, instrument_api, portfolio_cache, portfolio_utils
from backend.common import portfolio as portfolio_mod
from backend.common.data_providers import InvalidPayload, LocalDataProvider, _parse_json_body, _safe_json_load
from backend.config import config
from backend.routes import portfolio as portfolio_routes

_CORRUPT = InvalidPayload(
    "Invalid JSON in /srv/data/accounts/alex/isa.json: line 5 column 1: Expecting property name",
    source="alex/isa.json",
    reason="line 5 column 1: Expecting property name",
)
_EXPECTED_DETAIL = "Data file is invalid: alex/isa.json (line 5 column 1: Expecting property name)"


def _raise_corrupt(*_args, **_kwargs):
    raise _CORRUPT


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _write_conflicted_account(root: Path) -> Path:
    path = root / "alex" / "isa.json"
    path.parent.mkdir(parents=True)
    path.write_text('{\n  "owner": "alex",\n<<<<<<< Updated upstream\n  "currency": "GBP"\n}\n', encoding="utf-8")
    return path


class TestSafeJsonLoad:
    def test_malformed_json_names_the_file_and_position(self, tmp_path: Path) -> None:
        path = _write_conflicted_account(tmp_path)

        with pytest.raises(InvalidPayload) as exc_info:
            _safe_json_load(path)

        exc = exc_info.value
        assert exc.source == "alex/isa.json"
        assert exc.reason is not None and exc.reason.startswith("line 3 column 1:")
        assert str(path) in str(exc)
        assert isinstance(exc.__cause__, json.JSONDecodeError)

    def test_stays_a_value_error_so_loaders_can_skip_the_file(self, tmp_path: Path) -> None:
        path = _write_conflicted_account(tmp_path)

        with pytest.raises(ValueError):
            _safe_json_load(path)

    def test_empty_file_is_labelled(self, tmp_path: Path) -> None:
        path = tmp_path / "alex" / "isa.json"
        path.parent.mkdir(parents=True)
        path.write_text("  \n", encoding="utf-8")

        with pytest.raises(InvalidPayload) as exc_info:
            _safe_json_load(path)

        assert exc_info.value.source == "alex/isa.json"
        assert exc_info.value.reason == "empty file"

    def test_s3_body_is_labelled_like_a_local_file(self) -> None:
        body = io.BytesIO(b'{\n  "owner": "alex",\n<<<<<<< Updated upstream\n}')

        with pytest.raises(InvalidPayload) as exc_info:
            _parse_json_body(body, "s3://bucket/accounts/alex/isa.json")

        exc = exc_info.value
        assert exc.source == "alex/isa.json"
        assert exc.reason is not None and exc.reason.startswith("line 3 column 1:")

    def test_local_provider_keeps_the_source_label(self, tmp_path: Path) -> None:
        _write_conflicted_account(tmp_path)

        with pytest.raises(InvalidPayload) as exc_info:
            LocalDataProvider().load_account("alex", "isa", tmp_path)

        assert exc_info.value.source == "alex/isa.json"


@pytest.mark.parametrize(
    "path",
    [
        "/portfolio-group/all",
        "/portfolio-group/all/sectors",
        "/portfolio-group/all/regions",
        "/portfolio-group/all/instruments",
    ],
)
def test_group_routes_report_the_corrupt_file(client, monkeypatch, path) -> None:
    monkeypatch.setattr(portfolio_routes, "_build_group_portfolio", _raise_corrupt)

    resp = client.get(path)

    assert resp.status_code == 500
    assert resp.json() == {"detail": _EXPECTED_DETAIL}


def test_group_performance_route_reports_the_corrupt_file(client, monkeypatch) -> None:
    monkeypatch.setattr(portfolio_utils, "compute_group_max_drawdown", _raise_corrupt)

    resp = client.get("/performance-group/all/max-drawdown")

    assert resp.status_code == 500
    assert resp.json() == {"detail": _EXPECTED_DETAIL}


def test_fund_upkeep_group_route_reports_the_corrupt_file(client, monkeypatch) -> None:
    # Unique slug: cached_group_portfolio would otherwise serve a cached build.
    monkeypatch.setattr(group_portfolio, "build_group_portfolio", _raise_corrupt)

    resp = client.get("/fund-upkeep/group/corrupt-upkeep/all-in-cost")

    assert resp.status_code == 500
    assert resp.json() == {"detail": _EXPECTED_DETAIL}


def test_opportunities_group_route_reports_the_corrupt_file(client, monkeypatch) -> None:
    # This route catches bare Exception, the widest net to regress back to 404.
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(instrument_api, "instrument_summaries_for_group", _raise_corrupt)

    resp = client.get("/opportunities", params={"group": "corrupt-opportunities", "days": 1})

    assert resp.status_code == 500
    assert resp.json() == {"detail": _EXPECTED_DETAIL}


def test_group_movers_route_reports_the_corrupt_file(client, monkeypatch) -> None:
    # Like /opportunities, /movers catches bare Exception around the summaries.
    monkeypatch.setattr(instrument_api, "instrument_summaries_for_group", _raise_corrupt)

    resp = client.get("/portfolio-group/corrupt-movers/movers", params={"days": 1})

    assert resp.status_code == 500
    assert resp.json() == {"detail": _EXPECTED_DETAIL}


def test_log_line_carries_the_full_path_and_position(client, monkeypatch) -> None:
    logged: list[str] = []

    def _capture(msg, *args, **_kwargs):
        logged.append(msg % args)

    monkeypatch.setattr(app_module.logger, "warning", _capture)
    monkeypatch.setattr(portfolio_routes, "_build_group_portfolio", _raise_corrupt)

    client.get("/portfolio-group/all")

    assert any("/srv/data/accounts/alex/isa.json" in line and "line 5 column 1" in line for line in logged)


def test_owner_portfolio_reports_the_corrupt_file(client, monkeypatch) -> None:
    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", _raise_corrupt)

    resp = client.get("/portfolio/alex")

    assert resp.status_code == 500
    assert resp.json() == {"detail": _EXPECTED_DETAIL}


def test_response_never_carries_the_server_path(client, monkeypatch) -> None:
    monkeypatch.setattr(portfolio_routes, "_build_group_portfolio", _raise_corrupt)

    resp = client.get("/portfolio-group/all")

    assert "/srv/data" not in resp.text


@pytest.fixture
def corrupt_alex_root(tmp_path, monkeypatch) -> Path:
    """Real files: steve is valid, alex's ISA carries a committed conflict marker.

    Nothing in the load chain is stubbed (``_safe_json_load`` -> ``load_account``
    -> ``build_owner_portfolio`` / ``build_group_portfolio``), only price lookups,
    since there is no price history offline.
    """
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(instrument_api, "_price_and_changes", lambda ticker: {})
    monkeypatch.setattr(portfolio_utils, "_window_closes", lambda *a, **k: None)
    portfolio_cache.invalidate_group_portfolios()
    for owner in ("steve", "alex"):
        (tmp_path / owner).mkdir()
        (tmp_path / owner / "person.json").write_text(json.dumps({"owner": owner}))
    steve_isa = {
        "owner": "steve",
        "account_type": "ISA",
        "currency": "GBP",
        "holdings": [{"ticker": "CASH.GBP", "units": 100.0, "cost_basis_gbp": 100.0}],
    }
    (tmp_path / "steve" / "isa.json").write_text(json.dumps(steve_isa))
    (tmp_path / "alex" / "isa.json").write_text(
        '{\n  "owner": "alex",\n  "account_type": "ISA",\n  "currency": "GBP",\n'
        '<<<<<<< Updated upstream\n  "holdings": []\n}\n'
    )
    yield tmp_path
    portfolio_cache.invalidate_group_portfolios()


@pytest.mark.parametrize("path", ["/portfolio-group/all", "/portfolio/alex"])
def test_real_corrupt_file_is_named_end_to_end(corrupt_alex_root, path) -> None:
    # Built after the fixture: create_app caches accounts_root in app.state.
    client = TestClient(create_app())

    resp = client.get(path)

    assert resp.status_code == 500, resp.text
    detail = resp.json()["detail"]
    assert detail.startswith("Data file is invalid: alex/isa.json (line 5 column 1:")
    assert str(corrupt_alex_root) not in resp.text


def test_real_corrupt_file_leaves_other_groups_loading(corrupt_alex_root) -> None:
    # adults = lucy + steve; neither file is broken, so it still loads.
    resp = TestClient(create_app()).get("/portfolio-group/adults")

    assert resp.status_code == 200, resp.text


def test_unknown_group_is_still_not_found(client, monkeypatch) -> None:
    def _unknown(*_args, **_kwargs):
        raise ValueError("Unknown group slug: 'nope'")

    monkeypatch.setattr(portfolio_routes, "_build_group_portfolio", _unknown)

    resp = client.get("/portfolio-group/nope")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Group not found"}


def test_payload_without_source_gets_a_generic_detail(client, monkeypatch) -> None:
    def _bare(*_args, **_kwargs):
        raise InvalidPayload("bad data")

    monkeypatch.setattr(portfolio_routes, "_build_group_portfolio", _bare)

    resp = client.get("/portfolio-group/all")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Data file is invalid"}
