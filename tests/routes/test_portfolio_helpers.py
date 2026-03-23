from pathlib import Path
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from backend.common.account_models import PersonMetadata
from backend.routes import portfolio as portfolio_routes
from backend.common import data_loader


def _make_request_with_root(tmp_path: Path) -> Request:
    app = MagicMock()
    app.state.accounts_root = str(tmp_path)
    scope = {"type": "http", "app": app}
    return Request(scope=scope)


def test_normalise_owner_entry_enriches_accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    owner_dir = tmp_path / "Alex"
    owner_dir.mkdir()
    (owner_dir / "isa.json").write_text("{}", encoding="utf-8")
    (owner_dir / "sipp.json").write_text("{}", encoding="utf-8")
    (owner_dir / "alex_transactions.json").write_text("{}", encoding="utf-8")

    def fake_load_person_metadata(owner: str, accounts_root: Path) -> PersonMetadata:
        assert owner == "Alex"
        assert accounts_root == tmp_path
        return PersonMetadata(preferred_name="Alexandra")

    monkeypatch.setattr(
        portfolio_routes.data_loader,
        "load_person_metadata",
        fake_load_person_metadata,
    )

    result = portfolio_routes._normalise_owner_entry(
        {"owner": "Alex", "accounts": []},
        tmp_path,
    )

    assert result is not None
    assert result["owner"] == "Alex"
    assert "isa" in result["accounts"] or "ISA" in result["accounts"]
    assert result.get("full_name") == "Alexandra"


def test_list_owner_summaries_filters_and_normalises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()
    (owner_dir / "isa.json").write_text("{}", encoding="utf-8")

    def fake_list_plots(accounts_root: Path, current_user: str | None):
        assert current_user is None
        return [{"owner": "alex", "accounts": ["isa", ""]}]

    def fake_load_person_metadata(owner: str, accounts_root: Path) -> PersonMetadata:
        assert accounts_root == tmp_path
        if owner == "alex":
            return PersonMetadata(display_name="Alex Example")
        return PersonMetadata()

    monkeypatch.setattr(
        portfolio_routes.data_loader,
        "list_plots",
        fake_list_plots,
    )
    monkeypatch.setattr(
        portfolio_routes.data_loader,
        "load_person_metadata",
        fake_load_person_metadata,
    )

    request = _make_request_with_root(tmp_path)
    result = portfolio_routes._list_owner_summaries(request, current_user=None)

    # _list_owner_summaries returns List[OwnerSummary] typed objects
    owners = [r.owner for r in result]
    assert "alex" in owners
    alex_entry = next(r for r in result if r.owner == "alex")
    assert alex_entry.full_name == "Alex Example"
