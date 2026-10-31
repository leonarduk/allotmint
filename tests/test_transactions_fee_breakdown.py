"""Stamp duty and FX charges recorded as parts of a trade's ``fees`` (#10493). Synthetic data only."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common.holdings_rebuild import rebuild_holdings_document
from backend.common.trade_fees import breakdown_error, split_fees
from backend.config import config


def _payload(**overrides):
    payload = {
        "owner": "alice",
        "account": "ISA",
        "ticker": "PFE",
        "date": "2024-05-01",
        "type": "BUY",
        "price_gbp": 10.0,
        "units": 100,
        "fees": 20.0,
        "reason": "diversify",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    return TestClient(create_app())


def _stored(tmp_path):
    return json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())["transactions"]


def _cost_basis(tmp_path):
    holdings = json.loads((tmp_path / "alice" / "isa.json").read_text())["holdings"]
    return next(h["cost_basis_gbp"] for h in holdings if h["ticker"] == "PFE")


# --- splitting fees --------------------------------------------------------


def test_split_counts_the_remainder_as_dealing():
    split = split_fees({"fees": 20.0, "stamp_duty": 5.0, "fx_charge": 2.0})
    assert split is not None
    assert split.dealing == pytest.approx(13.0)
    assert (split.stamp_duty, split.fx_charge, split.fits) == (5.0, 2.0, True)


def test_legacy_row_with_only_fees_is_all_dealing():
    assert split_fees({"fees": 9.95}) == (9.95, 0.0, 0.0, True)


def test_unknown_fees_stay_unknown_even_with_a_breakdown():
    assert split_fees({"stamp_duty": 5.0}) is None


def test_breakdown_larger_than_fees_is_ignored_and_flagged():
    split = split_fees({"fees": 4.0, "stamp_duty": 5.0})
    assert split == (4.0, 0.0, 0.0, False)


@pytest.mark.parametrize(
    "fees, stamp, fx, ok",
    [
        (None, None, None, True),
        (20.0, None, None, True),
        (20.0, 5.0, 2.0, True),
        (20.0, 20.0, 0.0, True),
        (20.0, 15.0, 5.005, True),  # within a penny: split rounding
        (20.0, 15.0, 6.0, False),
        (None, 5.0, None, False),
    ],
)
def test_breakdown_error(fees, stamp, fx, ok):
    assert (breakdown_error(fees, stamp, fx) is None) is ok


# --- cost basis ------------------------------------------------------------


def test_breakdown_does_not_change_the_cost_basis():
    def cost(**extra):
        tx = {"type": "BUY", "ticker": "X", "units": 100, "price_gbp": 10.0, "fees": 20.0, "date": "2024-01-01"}
        doc = rebuild_holdings_document({"transactions": [{**tx, **extra}]}, "a", "isa")
        return doc["holdings"][0]["cost_basis_gbp"]

    assert cost() == pytest.approx(1_020.0)
    assert cost(stamp_duty=5.0, fx_charge=2.0) == pytest.approx(1_020.0)


# --- routes ----------------------------------------------------------------


def test_create_stores_the_breakdown_and_counts_fees_once(client, tmp_path):
    resp = client.post("/transactions", json=_payload(stamp_duty=5.0, fx_charge=2.0))
    assert resp.status_code == 201
    assert (resp.json()["stamp_duty"], resp.json()["fx_charge"]) == (5.0, 2.0)
    stored = _stored(tmp_path)[0]
    assert (stored["fees"], stored["stamp_duty"], stored["fx_charge"]) == (20.0, 5.0, 2.0)
    assert _cost_basis(tmp_path) == pytest.approx(1_020.0)


def test_create_without_a_breakdown_stores_no_new_keys(client, tmp_path):
    assert client.post("/transactions", json=_payload()).status_code == 201
    stored = _stored(tmp_path)[0]
    assert "stamp_duty" not in stored and "fx_charge" not in stored


@pytest.mark.parametrize(
    "overrides",
    [
        {"stamp_duty": 15.0, "fx_charge": 6.0},  # exceeds fees
        {"fees": None, "stamp_duty": 5.0},  # no total to be part of
        {"stamp_duty": -1.0},
    ],
)
def test_create_rejects_an_inconsistent_breakdown(client, overrides):
    assert client.post("/transactions", json=_payload(**overrides)).status_code == 422


def test_cash_row_drops_the_breakdown(client, tmp_path):
    body = {
        "owner": "alice",
        "account": "ISA",
        "date": "2024-05-01",
        "type": "FEES",
        "amount_minor": 500,
        "fees": 1.0,
        "stamp_duty": 1.0,
        "reason": "statement",
    }
    assert client.post("/transactions", json=body).status_code == 201
    stored = _stored(tmp_path)[0]
    assert "stamp_duty" not in stored and "fees" not in stored


def test_update_keeps_the_breakdown_while_fees_are_unchanged(client, tmp_path):
    created = client.post("/transactions", json=_payload(stamp_duty=5.0, fx_charge=2.0)).json()
    # The trade editors do not send the breakdown; editing units keeps it.
    resp = client.put(f"/transactions/{created['id']}", json=_payload(units=50))
    assert resp.status_code == 200
    assert (resp.json()["stamp_duty"], resp.json()["fx_charge"]) == (5.0, 2.0)


def test_update_with_new_fees_drops_an_omitted_breakdown(client, tmp_path):
    created = client.post("/transactions", json=_payload(stamp_duty=5.0, fx_charge=2.0)).json()
    resp = client.put(f"/transactions/{created['id']}", json=_payload(fees=3.0, stamp_duty=1.0))
    assert resp.status_code == 200
    stored = _stored(tmp_path)[0]
    assert stored["fees"] == 3.0 and stored["stamp_duty"] == 1.0
    assert "fx_charge" not in stored


def test_update_rejects_a_part_that_no_longer_fits_with_the_kept_one(client, tmp_path):
    created = client.post("/transactions", json=_payload(stamp_duty=5.0, fx_charge=2.0)).json()
    # fees unchanged, so the stored FX charge (2) is kept: 19 + 2 > 20.
    resp = client.put(f"/transactions/{created['id']}", json=_payload(stamp_duty=19.0))
    assert resp.status_code == 422
    assert _stored(tmp_path)[0]["stamp_duty"] == 5.0


def test_split_pro_rates_the_breakdown(client, tmp_path):
    created = client.post("/transactions", json=_payload(stamp_duty=5.0, fx_charge=2.0)).json()
    resp = client.post(f"/transactions/{created['id']}/split", json={"units": 25})
    assert resp.status_code == 200
    first, second = _stored(tmp_path)
    assert (first["fees"], first["stamp_duty"], first["fx_charge"]) == (5.0, 1.25, 0.5)
    assert (second["fees"], second["stamp_duty"], second["fx_charge"]) == (15.0, 3.75, 1.5)
