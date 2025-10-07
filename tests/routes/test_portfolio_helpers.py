from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.requests import Request

from backend.routes import portfolio as portfolio_routes


@pytest.fixture
def tmp_owner_dir(tmp_path: Path) -> Path:
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()
    return owner_dir


async def _empty_receive() -> dict:
    return {"type": "http.request"}


def _make_request_with_root(root: Path) -> Request:
    app = Starlette()
    app.state.accounts_root = root
    scope = {
        "type": "http",
        "app": app,
        "method": "GET",
        "path": "/owners",
        "headers": [],
    }
    return Request(scope, _empty_receive)


def test_collect_account_stems_filters_noise(tmp_owner_dir: Path) -> None:
    (tmp_owner_dir / "ISA.json").write_text("{}", encoding="utf-8")
    (tmp_owner_dir / "isa.json").write_text("{}", encoding="utf-8")
    (tmp_owner_dir / "GIA.JSON").write_text("{}", encoding="utf-8")
    (tmp_owner_dir / "person.json").write_text("{}", encoding="utf-8")
    (tmp_owner_dir / "notes.txt").write_text("notes", encoding="utf-8")
    (tmp_owner_dir / "isa_transactions.json").write_text("{}", encoding="utf-8")
    (tmp_owner_dir / "notes").mkdir()

    stems = portfolio_routes._collect_account_stems(tmp_owner_dir)

    assert stems == ["GIA", "ISA"]


@pytest.mark.parametrize(
    "artifact_name",
    ["alex_transactions.json", "alex_transactions"],
)
def test_has_transactions_artifact_detects_matches(
    tmp_owner_dir: Path, artifact_name: str
) -> None:
    target = tmp_owner_dir / artifact_name
    if target.suffix:
        target.write_text("{}", encoding="utf-8")
    else:
        target.mkdir()

    assert portfolio_routes._has_transactions_artifact(tmp_owner_dir, "Alex") is True


def test_normalise_owner_entry_enriches_accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()
    (owner_dir / "isa.json").write_text("{}", encoding="utf-8")
    (owner_dir / "sipp.json").write_text("{}", encoding="utf-8")
    (owner_dir / "alex_transactions.json").write_text("{}", encoding="utf-8")

    def fake_load_person_meta(owner: str, accounts_root: Path):
        assert owner == "Alex"
        assert accounts_root == tmp_path
        return {"preferred_name": "Alexandra"}

    monkeypatch.setattr(
        portfolio_routes.data_loader,
        "load_person_meta",
        fake_load_person_meta,
    )

    result = portfolio_routes._normalise_owner_entry(
        {"owner": "  Alex  ", "accounts": [" isa", "GIA", "ISA"]},
        tmp_path,
    )

    assert result == {
        "owner": "Alex",
        "full_name": "Alexandra",
        "accounts": ["isa", "GIA", "sipp"],
        "has_transactions_artifact": True,
    }


def test_list_owner_summaries_merges_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    (demo_dir / "isa.json").write_text("{}", encoding="utf-8")
    (demo_dir / "demo_transactions.json").write_text("{}", encoding="utf-8")

    alex_dir = tmp_path / "alex"
    alex_dir.mkdir()
    (alex_dir / "isa.json").write_text("{}", encoding="utf-8")

    def fake_list_plots(accounts_root: Path, current_user: str | None):
        assert accounts_root == tmp_path
        assert current_user is None
        return [{"owner": "alex", "accounts": ["isa", ""]}]

    def fake_load_person_meta(owner: str, accounts_root: Path):
        assert accounts_root == tmp_path
        if owner == "alex":
            return {"display_name": "Alex Example"}
        if owner == "demo":
            return {"full_name": "Demo Account"}
        return {}

    monkeypatch.setattr(
        portfolio_routes.data_loader, "list_plots", fake_list_plots
    )
    monkeypatch.setattr(
        portfolio_routes.data_loader,
        "load_person_meta",
        fake_load_person_meta,
    )

    request = _make_request_with_root(tmp_path)

    summaries = portfolio_routes._list_owner_summaries(request)

    owners = {summary.owner: summary for summary in summaries}
    assert set(owners) == {"alex", "demo"}
    assert owners["alex"].accounts == ["isa"]
    assert owners["alex"].full_name == "Alex Example"
    assert owners["demo"].full_name == "Demo Account"
    assert owners["demo"].has_transactions_artifact is True
