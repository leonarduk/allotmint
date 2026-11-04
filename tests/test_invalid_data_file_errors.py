"""A corrupt data file is reported as such, not as a missing group (#11428)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import portfolio as portfolio_mod
from backend.common import portfolio_utils
from backend.common.data_providers import InvalidPayload, LocalDataProvider, _safe_json_load
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


def test_owner_portfolio_reports_the_corrupt_file(client, monkeypatch) -> None:
    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", _raise_corrupt)

    resp = client.get("/portfolio/alex")

    assert resp.status_code == 500
    assert resp.json() == {"detail": _EXPECTED_DETAIL}


def test_response_never_carries_the_server_path(client, monkeypatch) -> None:
    monkeypatch.setattr(portfolio_routes, "_build_group_portfolio", _raise_corrupt)

    resp = client.get("/portfolio-group/all")

    assert "/srv/data" not in resp.text


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
