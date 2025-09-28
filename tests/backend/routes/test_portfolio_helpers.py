import types
from pathlib import Path

import pytest

from backend.routes import portfolio


def _write_json(path: Path) -> None:
    path.write_text("{}", encoding="utf-8")


def test_collect_account_stems_filters_metadata_and_transactions(tmp_path: Path) -> None:
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()

    for filename in (
        "person.json",
        "Notes.JSON",
        "config.Json",
        "isa.json",
        "ISA.JSON",
        "brokerage.json",
        "Brokerage.JSON",
        "isa_transactions.json",
        "sipp_TRANSACTIONS.JSON",
    ):
        _write_json(owner_dir / filename)

    stems = portfolio._collect_account_stems(owner_dir)

    normalised = {stem.casefold() for stem in stems}
    assert normalised == {"brokerage", "isa"}
    assert all(not stem.casefold().endswith("_transactions") for stem in stems)
    assert all(
        stem.casefold()
        not in {"person", "config", "notes", "settings", "approvals", "approval_requests"}
        for stem in stems
    )


def test_has_transactions_artifact_detects_file_and_directory(tmp_path: Path) -> None:
    owner_dir = tmp_path / "demo"
    owner_dir.mkdir()
    _write_json(owner_dir / "demo_transactions.json")
    (owner_dir / "demo_transactions").mkdir()

    assert portfolio._has_transactions_artifact(owner_dir, "demo") is True


def test_build_demo_summary_upgrades_default_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    accounts_root = tmp_path / "accounts"
    demo_dir = accounts_root / "demo"
    demo_dir.mkdir(parents=True)
    _write_json(demo_dir / "demo.json")

    def fake_resolve_owner_directory(root: Path, owner: str) -> Path | None:
        candidate = accounts_root / owner
        return candidate if candidate.exists() else None

    monkeypatch.setattr(portfolio, "resolve_owner_directory", fake_resolve_owner_directory)

    monkeypatch.setattr(
        portfolio.data_loader,
        "load_person_meta",
        lambda owner, root: {"full_name": "demo"},
    )

    summary = portfolio._build_demo_summary(accounts_root)
    assert summary["owner"] == "demo"
    assert summary["full_name"] == "Demo"
    assert "demo" in {account.casefold() for account in summary["accounts"]}

    def raising_meta(owner: str, root: Path) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr(portfolio.data_loader, "load_person_meta", raising_meta)

    fallback = portfolio._build_demo_summary(accounts_root)
    assert fallback["owner"] == "demo"
    assert fallback["full_name"] == "Demo"
    assert "demo" in {account.casefold() for account in fallback["accounts"]}


def test_list_owner_summaries_appends_demo_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()

    alex_dir = accounts_root / "alex"
    alex_dir.mkdir()
    _write_json(alex_dir / "isa.json")

    demo_dir = accounts_root / "demo"
    demo_dir.mkdir()
    _write_json(demo_dir / "demo.json")

    state = types.SimpleNamespace()
    request = types.SimpleNamespace(app=types.SimpleNamespace(state=state))

    def fake_resolve_accounts_root(_request, *, allow_missing: bool = False):
        return accounts_root

    def fake_resolve_owner_directory(root: Path, owner: str) -> Path | None:
        candidate = accounts_root / owner
        return candidate if candidate.exists() else None

    call_counter = {"count": 0}

    def fake_list_plots(root: Path, current_user):
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            return [{"owner": "alex", "accounts": ["isa"]}]
        return []

    def fake_load_person_meta(owner: str, root: Path) -> dict:
        return {"full_name": owner.lower()}

    monkeypatch.setattr(portfolio, "resolve_accounts_root", fake_resolve_accounts_root)
    monkeypatch.setattr(portfolio, "resolve_owner_directory", fake_resolve_owner_directory)
    monkeypatch.setattr(portfolio.data_loader, "list_plots", fake_list_plots)
    monkeypatch.setattr(portfolio.data_loader, "load_person_meta", fake_load_person_meta)

    first_result = portfolio._list_owner_summaries(request)
    assert [summary.owner for summary in first_result] == ["alex", "demo"]

    second_result = portfolio._list_owner_summaries(request)
    assert [summary.owner for summary in second_result] == ["demo"]
