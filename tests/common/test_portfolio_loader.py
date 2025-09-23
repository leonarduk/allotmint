import json
import logging
from pathlib import Path

import pytest

from backend.common import portfolio_loader
from backend.common.portfolio_loader import rebuild_account_holdings


def test_rebuild_account_holdings(tmp_path: Path) -> None:
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    tx_file = owner_dir / "ISA_transactions.json"
    tx_data = {
        "currency": "GBP",
        "transactions": [
            {"type": "BUY", "ticker": "ABC", "shares": 200_000_000, "date": "2024-01-10"},
            {"type": "SELL", "ticker": "ABC", "shares": 50_000_000, "date": "2024-02-15"},
            {"type": "TRANSFER_IN", "ticker": "XYZ", "shares": 150_000_000, "date": "2024-03-20"},
            {"type": "TRANSFER_OUT", "ticker": "XYZ", "shares": 50_000_000, "date": "2024-04-25"},
            {"type": "REMOVAL", "ticker": "XYZ", "shares": 25_000_000, "date": "2024-05-30"},
            {"type": "DEPOSIT", "amount_minor": 10000},
            {"type": "WITHDRAWAL", "amount_minor": 5000},
            {"type": "DIVIDENDS", "amount_minor": 2500},
        ],
    }
    tx_file.write_text(json.dumps(tx_data))

    result = rebuild_account_holdings("alice", "isa", accounts_root=tmp_path)

    holdings = {h["ticker"]: h for h in result["holdings"]}

    assert holdings["ABC"]["units"] == pytest.approx(1.5)
    assert holdings["ABC"]["acquired_date"] == "2024-01-10"

    assert holdings["XYZ"]["units"] == pytest.approx(0.75)
    assert holdings["XYZ"]["acquired_date"] == "2024-03-20"

    assert holdings["CASH.GBP"]["units"] == pytest.approx(75.0)


def test_rebuild_account_holdings_missing_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR, logger="portfolio_loader")

    result = rebuild_account_holdings("bob", "isa", accounts_root=tmp_path)

    assert result == {}
    assert "Transaction file missing" in caplog.text


def test_load_accounts_for_owner_missing_file(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="portfolio_loader")

    def _raise_missing(owner: str, account: str) -> dict:
        raise FileNotFoundError

    monkeypatch.setattr(portfolio_loader, "load_account", _raise_missing)

    accounts = portfolio_loader._load_accounts_for_owner("alex", ["isa"])

    assert accounts == []
    assert "Account file missing: alex/isa.json" in caplog.text


def test_load_accounts_for_owner_json_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="portfolio_loader")

    def _raise_decode_error(owner: str, account: str) -> dict:
        raise json.JSONDecodeError("bad", "{}", 0)

    monkeypatch.setattr(portfolio_loader, "load_account", _raise_decode_error)

    accounts = portfolio_loader._load_accounts_for_owner("alex", ["isa"])

    assert accounts == []
    assert "Failed to parse alex/isa.json" in caplog.text


@pytest.fixture
def patched_portfolio_loader(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    owners = [
        {"owner": "alex", "accounts": ["isa"]},
        {"owner": "beth", "accounts": ["sipp", "taxable"]},
    ]

    def _fake_list_plots() -> list[dict[str, object]]:
        return owners

    def _fake_person(owner: str) -> dict[str, str]:
        return {"owner": owner, "full_name": owner.title()}

    def _fake_account(owner: str, account: str) -> dict[str, str]:
        return {
            "owner": owner,
            "account": account.upper(),
            "path": f"{owner}/{account}.json",
        }

    monkeypatch.setattr(portfolio_loader, "list_plots", _fake_list_plots)
    monkeypatch.setattr(portfolio_loader, "load_person_meta", _fake_person)
    monkeypatch.setattr(portfolio_loader, "load_account", _fake_account)

    return owners


def test_list_portfolios_aggregates_owners(patched_portfolio_loader: list[dict[str, object]]) -> None:
    result = portfolio_loader.list_portfolios()

    expected = [
        {
            "owner": row["owner"],
            "person": {"owner": row["owner"], "full_name": row["owner"].title()},
            "accounts": [
                {
                    "owner": row["owner"],
                    "account": account.upper(),
                    "path": f"{row['owner']}/{account}.json",
                }
                for account in row["accounts"]
            ],
        }
        for row in patched_portfolio_loader
    ]

    assert result == expected


def test_load_portfolio_case_insensitive(
    patched_portfolio_loader: list[dict[str, object]]
) -> None:
    all_portfolios = portfolio_loader.list_portfolios()

    beth_portfolio = portfolio_loader.load_portfolio("BeTh")

    assert beth_portfolio == all_portfolios[1]
    assert portfolio_loader.load_portfolio("charlie") is None
