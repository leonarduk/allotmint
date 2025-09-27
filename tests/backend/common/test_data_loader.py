import json
from contextvars import ContextVar
from pathlib import Path

import pytest

from backend.common.data_loader import (
    DATA_BUCKET_ENV,
    ResolvedPaths,
    _list_local_plots,
    _safe_json_load,
    load_person_meta,
    load_virtual_portfolio,
    resolve_paths,
    save_virtual_portfolio,
    list_plots,
)
from backend.common.virtual_portfolio import VirtualPortfolio
from backend.config import Config


def _write_owner(
    root: Path,
    owner: str,
    accounts: list[str],
    viewers: list[str] | None = None,
    *,
    email: str | None = None,
) -> None:
    owner_dir = root / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    person_path = owner_dir / "person.json"
    viewers_data = viewers or []
    meta: dict[str, object] = {"viewers": viewers_data}
    if email:
        meta["email"] = email
    person_path.write_text(json.dumps(meta))
    for account in accounts:
        (owner_dir / f"{account}.json").write_text("{}")




class TestSafeJsonLoad:
    def test_parses_json_with_utf8_bom(self, tmp_path: Path) -> None:
        payload = {"key": "value"}
        path = tmp_path / "data.json"
        path.write_bytes(json.dumps(payload).encode("utf-8-sig"))

        result = _safe_json_load(path)

        assert result == payload

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError):
            _safe_json_load(path)

    def test_whitespace_only_raises_value_error(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.json"
        path.write_text(" \t\n  ")

        with pytest.raises(ValueError) as exc:
            _safe_json_load(path)

        assert str(exc.value) == f"Empty JSON file: {path}"


class TestLoadPersonMeta:
    def test_malformed_person_json_returns_empty_meta(self, tmp_path: Path) -> None:
        owner_dir = tmp_path / "alice"
        owner_dir.mkdir()
        person_path = owner_dir / "person.json"
        person_path.write_text("{invalid")

        with pytest.raises(json.JSONDecodeError):
            _safe_json_load(person_path)

        meta = load_person_meta("alice", data_root=tmp_path)

        assert meta == {}
        assert meta.get("viewers", []) == []


class TestResolvePaths:
    def test_with_relative_accounts_root(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        accounts_relative = Path("alt") / "accounts"
        absolute_accounts = (repo_dir / accounts_relative).resolve()
        absolute_accounts.mkdir(parents=True, exist_ok=True)

        result = resolve_paths(repo_root=repo_dir, accounts_root=accounts_relative)

        expected_virtual = absolute_accounts.parent / "virtual_portfolios"
        assert result == ResolvedPaths(repo_dir, absolute_accounts, expected_virtual)

    def test_with_absolute_accounts_root(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        absolute_accounts = tmp_path / "external" / "accounts"
        absolute_accounts.mkdir(parents=True, exist_ok=True)

        result = resolve_paths(repo_root=repo_dir, accounts_root=absolute_accounts)

        expected_virtual = absolute_accounts.parent / "virtual_portfolios"
        assert result == ResolvedPaths(repo_dir, absolute_accounts, expected_virtual)

    def test_handles_windows_style_absolute_paths(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        windows_accounts = "C:\\Users\\Example\\accounts"

        result = resolve_paths(repo_root=repo_dir, accounts_root=windows_accounts)

        expected_accounts = Path(windows_accounts).expanduser()
        expected_virtual = expected_accounts.parent / "virtual_portfolios"
        assert result == ResolvedPaths(repo_dir, expected_accounts, expected_virtual)


class TestVirtualPortfolioPersistence:
    def test_save_and_load_round_trip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo_dir = tmp_path / "repo"
        accounts_relative = Path("custom") / "accounts"
        accounts_dir = repo_dir / accounts_relative
        accounts_dir.mkdir(parents=True, exist_ok=True)

        cfg = Config()
        cfg.repo_root = repo_dir
        cfg.accounts_root = accounts_relative
        cfg.app_env = None
        monkeypatch.setattr("backend.common.data_loader.config", cfg)
        monkeypatch.delenv(DATA_BUCKET_ENV, raising=False)

        portfolio = VirtualPortfolio(id="vp-demo", name="demo", holdings=[])

        save_virtual_portfolio(portfolio)

        paths = resolve_paths(cfg.repo_root, cfg.accounts_root)
        expected_path = paths.virtual_pf_root / "demo.json"

        assert expected_path.exists()

        loaded = load_virtual_portfolio("demo")

        assert loaded is not None
        assert loaded.model_dump() == portfolio.model_dump()


class TestListLocalPlots:
    def _configure(self, monkeypatch: pytest.MonkeyPatch, repo_root: Path, accounts_root: Path, disable_auth: bool | None) -> None:
        cfg = Config()
        cfg.repo_root = repo_root
        cfg.accounts_root = accounts_root
        cfg.disable_auth = disable_auth
        cfg.app_env = None
        monkeypatch.setattr("backend.common.data_loader.config", cfg)
        monkeypatch.delenv(DATA_BUCKET_ENV, raising=False)

    def test_authentication_required_skips_special_accounts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=False)

        _write_owner(data_root, "demo", ["demo1"], viewers=[])
        _write_owner(data_root, "alice", ["alpha"], viewers=["alice"])

        result = _list_local_plots(data_root=data_root, current_user=None)

        assert result == []

    def test_enforces_viewer_permissions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=False)

        _write_owner(data_root, "alice", ["alpha"], viewers=["viewer"])
        _write_owner(data_root, "bob", ["beta"], viewers=["other"])
        _write_owner(data_root, "demo", ["demo1"], viewers=[])

        result = _list_local_plots(data_root=data_root, current_user="viewer")

        assert result == [
            {"owner": "alice", "accounts": ["alpha"]},
        ]

    def test_accepts_contextvar_current_user(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=False)

        _write_owner(data_root, "alice", ["alpha"], viewers=["viewer"])
        _write_owner(data_root, "demo", ["demo1"], viewers=[])

        user_var: ContextVar[str | None] = ContextVar("user", default=None)
        token = user_var.set("viewer")
        try:
            result = _list_local_plots(data_root=data_root, current_user=user_var)
        finally:
            user_var.reset(token)

        assert result == [
            {"owner": "alice", "accounts": ["alpha"]},
        ]

    def test_authentication_disabled_allows_anonymous_access(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=True)

        _write_owner(data_root, "demo", ["demo1"], viewers=[])
        _write_owner(data_root, "carol", ["gamma"], viewers=["other"])

        result = _list_local_plots(data_root=data_root, current_user=None)

        assert result == [
            {"owner": "carol", "accounts": ["gamma"]},
            {"owner": "demo", "accounts": ["demo1"]},
        ]

    def test_list_plots_with_explicit_root_includes_demo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=True)

        _write_owner(data_root, "demo", ["demo1"], viewers=[])
        _write_owner(data_root, "carol", ["gamma"], viewers=["other"])

        result = list_plots(data_root=data_root, current_user=None)

        assert result == [
            {"owner": "carol", "accounts": ["gamma"]},
            {"owner": "demo", "accounts": ["demo1"]},
        ]

    def test_allows_access_when_user_matches_owner_email(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=False)

        _write_owner(
            data_root,
            "alice",
            ["alpha"],
            viewers=[],
            email="alice@example.com",
        )
        _write_owner(data_root, "bob", ["beta"], viewers=["bob"], email="bob@example.com")

        result = _list_local_plots(data_root=data_root, current_user="alice@example.com")

        assert result == [
            {"owner": "alice", "accounts": ["alpha"]},
        ]
