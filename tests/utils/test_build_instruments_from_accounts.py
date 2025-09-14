import json
import pytest

from backend.utils.build_instruments_from_accounts import (
    split_ticker,
    best_name,
    infer_currency,
)


@pytest.mark.parametrize(
    "ticker,expected",
    [
        ("ABC.L", ("ABC", "L")),
        ("ABC", ("ABC", None)),
    ],
)
def test_split_ticker(ticker, expected):
    assert split_ticker(ticker) == expected


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("Short", "LongerName", "LongerName"),
        ("LongerName", "Short", "LongerName"),
        (None, "Beta", "Beta"),
        ("Alpha", None, "Alpha"),
        (None, None, None),
    ],
)
def test_best_name(a, b, expected):
    assert best_name(a, b) == expected


@pytest.mark.parametrize(
    "sym,exch,scaling,expected",
    [
        ("CASH", "GBP", {}, "GBP"),
        ("XYZ", "L", {"L": {"XYZ": 0.01}}, "GBX"),
        ("ABC", "N", {}, "USD"),
        ("DEF", "DE", {}, "EUR"),
        ("GHI", "TO", {}, None),
    ],
)
def test_infer_currency(sym, exch, scaling, expected):
    assert infer_currency(sym, exch, scaling) == expected


def test_build_and_write_instruments(monkeypatch, tmp_path):
    accounts_dir = tmp_path / "accounts"
    owner_dir = accounts_dir / "alice"
    owner_dir.mkdir(parents=True)
    acct_file = owner_dir / "acct.json"
    acct_file.write_text(
        json.dumps(
            {
                "holdings": [
                    {"ticker": "CASH.GBP"},
                    {"ticker": "ABC.L", "name": "ABC PLC"},
                ]
            }
        ),
        encoding="utf-8",
    )

    instruments_dir = tmp_path / "instruments"
    instruments_dir.mkdir()

    import backend.utils.build_instruments_from_accounts as bia

    monkeypatch.setattr(bia, "ACCOUNTS_DIR", accounts_dir)
    monkeypatch.setattr(bia, "INSTRUMENTS_DIR", instruments_dir)
    monkeypatch.setattr(bia, "SCALING_FILE", tmp_path / "scaling.json")

    instruments = bia.build_instruments()

    assert len(instruments) == 2

    cash = instruments["CASH.GBP"]
    assert cash["ticker"] == "CASH.GBP"
    assert cash["name"] == "Cash (GBP)"
    assert cash["currency"] == "GBP"
    assert cash["exchange"] is None

    equity = instruments["ABC.L"]
    assert equity["ticker"] == "ABC.L"
    assert equity["name"] == "ABC PLC"
    assert equity["currency"] == "GBP"
    assert equity["exchange"] == "L"

    bia.write_instrument_files(instruments)

    cash_file = instruments_dir / "Cash" / "GBP.json"
    equity_file = instruments_dir / "L" / "ABC.json"
    cash_data = json.loads(cash_file.read_text(encoding="utf-8"))
    equity_data = json.loads(equity_file.read_text(encoding="utf-8"))

    assert cash_data == {
        "ticker": "CASH.GBP",
        "name": "Cash (GBP)",
        "sector": None,
        "region": None,
        "exchange": None,
        "currency": "GBP",
    }
    assert equity_data == {
        "ticker": "ABC.L",
        "name": "ABC PLC",
        "sector": None,
        "region": None,
        "exchange": "L",
        "currency": "GBP",
    }
