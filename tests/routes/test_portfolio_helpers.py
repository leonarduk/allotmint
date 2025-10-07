from pathlib import Path

import pytest

from backend.routes import portfolio


def test_collect_account_stems_filters_metadata(tmp_path: Path) -> None:
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "isa.json").write_text("{}")
    (owner_dir / "ISA.json").write_text("{}")
    (owner_dir / "config.json").write_text("{}")
    (owner_dir / "alice_transactions.json").write_text("{}")
    (owner_dir / "notes.txt").write_text("ignored")
    (owner_dir / "gia.json").write_text("{}")

    stems = portfolio._collect_account_stems(owner_dir)

    assert stems == ["ISA", "gia"]


def test_has_transactions_artifact_detects_files_and_directories(tmp_path: Path) -> None:
    owner_dir = tmp_path / "Alice"
    owner_dir.mkdir()

    assert portfolio._has_transactions_artifact(owner_dir, "Alice") is False

    (owner_dir / "Alice_transactions.json").write_text("{}")
    assert portfolio._has_transactions_artifact(owner_dir, "Alice") is True

    (owner_dir / "ALICE_TRANSACTIONS").mkdir()
    assert portfolio._has_transactions_artifact(owner_dir, "alice") is True


@pytest.mark.parametrize(
    "entry, meta, expected",
    [
        ({"full_name": " Alice Example "}, {"display_name": "Ignored"}, "Alice Example"),
        ({}, {"preferred_name": " Ally "}, "Ally"),
        ({}, {}, "owner"),
    ],
)
def test_resolve_full_name(entry: dict[str, str], meta: dict[str, str], expected: str) -> None:
    result = portfolio._resolve_full_name("owner", entry, meta)
    assert result == expected


def test_normalise_owner_entry_combines_accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    accounts_root = tmp_path
    owner_dir = accounts_root / "Alice"
    owner_dir.mkdir()
    (owner_dir / "growth.json").write_text("{}")
    (owner_dir / "person.json").write_text("{}")
    (owner_dir / "Alice_transactions").mkdir()

    entry = {"owner": "Alice", "accounts": ["ISA", "isa", "custom", " "]}

    result = portfolio._normalise_owner_entry(
        entry,
        accounts_root,
        meta={"display_name": " Ally "},
    )

    assert result == {
        "owner": "Alice",
        "full_name": "Ally",
        "accounts": [
            "ISA",
            "custom",
            "growth",
            "brokerage",
            "savings",
            "approvals",
            "settings",
            "Alice_transactions",
        ],
    }


def test_normalise_owner_entry_returns_none_for_missing_owner(tmp_path: Path) -> None:
    result = portfolio._normalise_owner_entry({}, tmp_path)
    assert result is None
