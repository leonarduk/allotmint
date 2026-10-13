"""``/owners`` must list only real accounts, never owner metadata files (#10788)."""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from backend.common.account_models import ACCOUNT_METADATA_STEMS
from backend.routes import portfolio

_METADATA_FILES = ("person.json", "settings.json", "approvals.json", "pension-forecast.json")


def _make_owner(accounts_root: Path) -> None:
    owner_dir = accounts_root / "lucy"
    owner_dir.mkdir(parents=True)
    for filename in (*_METADATA_FILES, "isa.json", "isa_transactions.json", "pension-forecast-isa.json"):
        (owner_dir / filename).write_text("{}", encoding="utf-8")


def test_metadata_stems_cover_known_metadata_files() -> None:
    assert {"person", "settings", "approvals", "pension-forecast", "pension_forecast"} <= ACCOUNT_METADATA_STEMS


def test_owners_lists_only_real_accounts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    accounts_root = tmp_path / "accounts"
    _make_owner(accounts_root)

    monkeypatch.setattr(portfolio, "resolve_accounts_root", lambda _request, *, allow_missing=False: accounts_root)
    monkeypatch.setattr(
        portfolio,
        "resolve_owner_directory",
        lambda root, owner: (accounts_root / owner) if (accounts_root / owner).exists() else None,
    )
    monkeypatch.setattr(portfolio.data_loader, "load_person_meta", lambda owner, root: {"full_name": owner})
    request = types.SimpleNamespace(app=types.SimpleNamespace(state=types.SimpleNamespace()))

    summaries = portfolio._list_owner_summaries(request)

    lucy = next(summary for summary in summaries if summary.owner == "lucy")
    # A real account whose name merely contains a metadata word is kept.
    assert sorted(lucy.accounts) == ["isa", "pension-forecast-isa"]


def test_collect_account_stems_skips_pension_forecast(tmp_path: Path) -> None:
    _make_owner(tmp_path)

    assert portfolio._collect_account_stems(tmp_path / "lucy") == ["isa", "pension-forecast-isa"]
