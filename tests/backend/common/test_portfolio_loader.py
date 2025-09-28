import json
import logging
from pathlib import Path

import pytest

from backend.common import portfolio_loader
from backend.common.data_loader import ResolvedPaths
from backend.config import config


@pytest.fixture
def patched_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_dir = tmp_path / "repo"
    accounts_dir = repo_dir / "accounts"
    virtual_dir = repo_dir / "virtual_portfolios"
    virtual_dir.mkdir(parents=True)
    accounts_dir.mkdir(parents=True, exist_ok=True)

    resolved = ResolvedPaths(repo_dir, accounts_dir, virtual_dir)

    monkeypatch.setattr(config, "repo_root", repo_dir)
    monkeypatch.setattr(config, "accounts_root", accounts_dir)

    def _fake_resolve_paths(
        repo_root: Path | None = None, accounts_root: Path | None = None
    ) -> ResolvedPaths:
        return resolved

    monkeypatch.setattr(portfolio_loader, "resolve_paths", _fake_resolve_paths)
    return accounts_dir


def test_rebuild_account_holdings_scaling(
    patched_paths: Path,
) -> None:
    owner_dir = patched_paths / "alex"
    owner_dir.mkdir()
    tx_file = owner_dir / "ISA_transactions.json"
    tx_data = {
        "currency": "GBP",
        "transactions": [
            {"type": "BUY", "ticker": "ABC", "shares": 200_000_000, "date": "2024-01-10"},
            {"type": "BUY", "ticker": "ABC", "shares": 50_000_000, "date": "2024-03-10"},
            {"type": "SELL", "ticker": "ABC", "shares": 25_000_000, "date": "2024-04-01"},
            {"type": "TRANSFER_IN", "ticker": "XYZ", "shares": 150_000_000, "date": "2024-02-20"},
            {"type": "TRANSFER_IN", "ticker": "XYZ", "shares": 50_000_000, "date": "2024-04-20"},
            {"type": "TRANSFER_OUT", "ticker": "XYZ", "shares": 25_000_000, "date": "2024-05-01"},
            {"type": "DEPOSIT", "amount_minor": 12_500},
            {"type": "WITHDRAWAL", "amount_minor": 2_500},
        ],
    }
    tx_file.write_text(json.dumps(tx_data))

    result = portfolio_loader.rebuild_account_holdings("alex", "isa")

    assert result["owner"] == "alex"
    assert result["account_type"] == "ISA"
    assert result["currency"] == "GBP"

    holdings = {holding["ticker"]: holding for holding in result["holdings"]}

    abc = holdings["ABC"]
    assert abc["units"] == pytest.approx(2.25)
    assert abc["acquired_date"] == "2024-03-10"

    xyz = holdings["XYZ"]
    assert xyz["units"] == pytest.approx(1.75)
    assert xyz["acquired_date"] == "2024-04-20"

    cash = holdings["CASH.GBP"]
    assert cash["units"] == pytest.approx(100.0)


def test_rebuild_account_holdings_missing_file(
    patched_paths: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="portfolio_loader")

    result = portfolio_loader.rebuild_account_holdings("bob", "isa")

    assert result == {}
    assert "Transaction file missing" in caplog.text


def test_rebuild_account_holdings_bad_json(
    patched_paths: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="portfolio_loader")

    owner_dir = patched_paths / "carol"
    owner_dir.mkdir()
    tx_file = owner_dir / "SIPP_transactions.json"
    tx_file.write_text("{not valid json")

    result = portfolio_loader.rebuild_account_holdings("carol", "sipp")

    assert result == {}
    assert "Failed to read" in caplog.text
