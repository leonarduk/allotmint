"""ISIN vs exchange guard on instrument metadata writes (#9295)."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.instrument_admin as instrument_admin
from backend.common import instruments
from backend.common.isin import ForeignIsinError, check_isin_change, isin_fits_exchange

BRISTOL_MYERS = "US1101221083"
BLOOMSBURY = "GB0033147751"


@pytest.mark.parametrize(
    ("isin", "exchange", "expected"),
    [
        (BLOOMSBURY, "L", True),
        ("IE00B4L5Y983", "L", True),
        ("JE00B1VS3770", "L", True),
        (BRISTOL_MYERS, "L", False),
        ("IL0011301780", "LSE", False),
        (BRISTOL_MYERS, "N", True),
        (BLOOMSBURY, "NASDAQ", False),
        ("DE0006231004", "DE", True),
        (" us1101221083 ", "l", False),
        ("-", "L", None),
        ("", "L", None),
        (None, "L", None),
        ("NOTANISIN", "L", None),
        (BRISTOL_MYERS, "XYZ", None),
    ],
)
def test_isin_fits_exchange(isin, exchange, expected):
    assert isin_fits_exchange(isin, exchange) is expected


def test_check_isin_change_refuses_a_foreign_prefix_on_a_london_line():
    with pytest.raises(ForeignIsinError, match="US1101221083.*exchange L"):
        check_isin_change(BLOOMSBURY, BRISTOL_MYERS, "L")
    with pytest.raises(ForeignIsinError):
        check_isin_change(None, BRISTOL_MYERS, "L")


@pytest.mark.parametrize(
    ("existing", "new", "kwargs"),
    [
        (BRISTOL_MYERS, BRISTOL_MYERS, {}),  # unchanged: never re-judged
        (BRISTOL_MYERS, BRISTOL_MYERS.lower(), {}),  # unchanged ignoring case
        (BRISTOL_MYERS, BLOOMSBURY, {}),  # correcting to a fitting ISIN
        (BLOOMSBURY, None, {}),  # removing it
        (BLOOMSBURY, "", {}),
        (None, "AU000000BHP4", {"allow_foreign_isin": True}),  # depositary interest, confirmed
    ],
)
def test_check_isin_change_allows(existing, new, kwargs):
    check_isin_change(existing, new, "L", **kwargs)


@pytest.fixture
def instruments_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path)
    monkeypatch.delenv(instruments.METADATA_BUCKET_ENV, raising=False)
    return tmp_path


def _write(root, exchange, symbol, data):
    path = root / exchange / f"{symbol}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_save_refuses_overwriting_an_isin_with_a_foreign_one(instruments_dir):
    path = _write(instruments_dir, "L", "BMY", {"ticker": "BMY.L", "isin": BLOOMSBURY})
    with pytest.raises(ForeignIsinError):
        instruments.save_instrument_meta("BMY", "L", {"ticker": "BMY.L", "isin": BRISTOL_MYERS})
    assert json.loads(path.read_text(encoding="utf-8"))["isin"] == BLOOMSBURY


def test_save_refuses_a_foreign_isin_on_a_new_london_file(instruments_dir):
    with pytest.raises(ForeignIsinError):
        instruments.save_instrument_meta("WIX.L", {"ticker": "WIX.L", "isin": "IL0011301780"})
    assert not (instruments_dir / "L" / "WIX.json").exists()


def test_save_with_flag_writes_a_foreign_isin(instruments_dir):
    path = instruments.save_instrument_meta(
        "BHP", "L", {"ticker": "BHP.L", "isin": "AU000000BHP4"}, allow_foreign_isin=True
    )
    assert json.loads(path.read_text(encoding="utf-8"))["isin"] == "AU000000BHP4"


def test_save_keeps_an_existing_foreign_isin_on_unrelated_edits(instruments_dir):
    _write(instruments_dir, "L", "BHP", {"ticker": "BHP.L", "isin": "AU000000BHP4"})
    path = instruments.save_instrument_meta(
        "BHP", "L", {"ticker": "BHP.L", "isin": "AU000000BHP4", "grouping": "Mining"}
    )
    assert json.loads(path.read_text(encoding="utf-8"))["grouping"] == "Mining"


def test_save_over_an_unreadable_file_still_checks_the_new_isin(instruments_dir):
    path = instruments_dir / "L" / "BMY.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ForeignIsinError):
        instruments.save_instrument_meta("BMY", "L", {"ticker": "BMY.L", "isin": BRISTOL_MYERS})


def _client():
    app = FastAPI()
    app.include_router(instrument_admin.router)
    return TestClient(app)


def test_put_route_returns_422_for_a_foreign_isin_and_accepts_the_flag(instruments_dir):
    path = _write(instruments_dir, "L", "BMY", {"ticker": "BMY.L", "exchange": "L", "isin": BLOOMSBURY})
    client = _client()

    refused = client.put("/instrument/admin/L/BMY", json={"isin": BRISTOL_MYERS})
    assert refused.status_code == 422
    assert "US1101221083" in refused.json()["detail"]
    assert json.loads(path.read_text(encoding="utf-8"))["isin"] == BLOOMSBURY

    confirmed = client.put("/instrument/admin/L/BMY?allow_foreign_isin=true", json={"isin": BRISTOL_MYERS})
    assert confirmed.status_code == 200
    assert json.loads(path.read_text(encoding="utf-8"))["isin"] == BRISTOL_MYERS


def test_post_route_returns_422_for_a_foreign_isin(instruments_dir):
    resp = _client().post("/instrument/admin/L/WIX", json={"ticker": "WIX.L", "isin": "IL0011301780"})
    assert resp.status_code == 422
    assert not (instruments_dir / "L" / "WIX.json").exists()
