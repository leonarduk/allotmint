import json
import os
import sys
import time
from contextvars import ContextVar
from pathlib import Path

import pytest

import backend.common.data_loader as data_loader
from backend.common.account_models import OwnerSummaryRecord
from backend.common.data_loader import (
    DATA_BUCKET_ENV,
    ResolvedPaths,
    _build_owner_summary,
    _extract_account_names,
    _list_local_plots,
    _load_demo_owner,
    _merge_accounts,
    _safe_json_load,
    clear_local_owner_index_cache,
    list_plots,
    load_account_record,
    load_person_meta,
    load_person_metadata,
    load_virtual_portfolio,
    resolve_default_accounts_root,
    resolve_owner_dir,
    resolve_paths,
    save_virtual_portfolio,
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
    full_name: str | None = None,
) -> None:
    owner_dir = root / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    person_path = owner_dir / "person.json"
    viewers_data = viewers or []
    meta: dict[str, object] = {"viewers": viewers_data}
    if email:
        meta["email"] = email
    if full_name:
        meta["full_name"] = full_name
    person_path.write_text(json.dumps(meta))
    for account in accounts:
        (owner_dir / f"{account}.json").write_text("{}")


@pytest.fixture(autouse=True)
def _clear_owner_index_cache() -> None:
    clear_local_owner_index_cache()
    yield
    clear_local_owner_index_cache()

class TestExtractAccountNames:
    def test_dedupes_and_filters_metadata(self, tmp_path: Path) -> None:
        owner_dir = tmp_path / "alice"
        owner_dir.mkdir()
        for filename in [
            "isa.json",
            "ISA.json",
            "config.json",
            "sipp_transactions.json",
            "GIA.json",
            "notes.txt",
        ]:
            path = owner_dir / filename
            if path.suffix == ".json":
                path.write_text("{}")
            else:
                path.write_text("")

        result = _extract_account_names(owner_dir)

        assert result == ["GIA", "ISA"]


class TestMergeAccounts:
    def test_merges_unique_accounts_and_full_name(self) -> None:
        base = {"owner": "alice", "accounts": ["ISA"]}
        extra = {"accounts": ["isa", "GIA", 123], "full_name": "Alice Example"}

        _merge_accounts(base, extra)

        assert base["full_name"] == "Alice Example"
        assert base["accounts"] == ["ISA", "GIA"]


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


class TestBuildOwnerSummary:
    def test_prefers_full_name_and_strips_whitespace(self) -> None:
        accounts = ["ISA"]
        meta = {
            "full_name": "  Alex Example  ",
            "display_name": "Alex Display",
            "preferred_name": "Alex Preferred",
        }

        result = _build_owner_summary("alex", accounts, meta)

        assert result == {
            "owner": "alex",
            "accounts": accounts,
            "full_name": "Alex Example",
        }

    def test_defaults_to_owner_slug_when_names_missing(self) -> None:
        accounts = ["SIPP"]
        meta = {"full_name": " ", "display_name": "", "preferred_name": None}

        result = _build_owner_summary("alex", accounts, meta)

        assert result == {
            "owner": "alex",
            "accounts": accounts,
        }

    def test_includes_email_when_present(self) -> None:
        accounts = ["ISA"]
        meta = {"email": "alex@example.com"}

        result = _build_owner_summary("alex", accounts, meta)

        assert result["email"] == "alex@example.com"


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

    def test_extracts_full_name_when_present(self, tmp_path: Path) -> None:
        owner_dir = tmp_path / "alice"
        owner_dir.mkdir()
        person_path = owner_dir / "person.json"
        person_path.write_text(json.dumps({"full_name": "Alice Example", "viewers": []}))

        meta = load_person_meta("alice", data_root=tmp_path)

        assert meta["full_name"] == "Alice Example"

    def test_invalid_viewers_drops_key_preserves_other_fields(self, tmp_path: Path) -> None:
        # Non-list viewers is invalid: the viewers key is dropped but other valid
        # fields are preserved. data_providers._extract_person_meta handles this.
        owner_dir = tmp_path / "alice"
        owner_dir.mkdir()
        (owner_dir / "person.json").write_text(json.dumps({"full_name": "Alice", "viewers": "bad"}))

        assert load_person_meta("alice", data_root=tmp_path) == {"full_name": "Alice"}

    def test_load_person_metadata_returns_typed_model(self, tmp_path: Path) -> None:
        owner_dir = tmp_path / "alice"
        owner_dir.mkdir()
        (owner_dir / "person.json").write_text(
            json.dumps(
                {
                    "full_name": " Alice Example ",
                    "email": "alice@example.com",
                    "viewers": [" bob@example.com "],
                }
            )
        )

        meta = load_person_metadata("alice", data_root=tmp_path)

        assert meta.full_name == "Alice Example"
        assert meta.email == "alice@example.com"
        assert meta.viewers == ["bob@example.com"]

    def test_load_person_metadata_rejects_malformed_viewers(self, tmp_path: Path) -> None:
        owner_dir = tmp_path / "alice"
        owner_dir.mkdir()
        (owner_dir / "person.json").write_text(
            json.dumps({"dob": "1980-01-01", "viewers": " bob@example.com "})
        )

        with pytest.raises(Exception, match="viewers must be a list"):
            load_person_metadata("alice", data_root=tmp_path)

    def test_person_metadata_accepts_date_like_dob_values(self) -> None:
        from datetime import date

        meta = data_loader.PersonMetadata.model_validate({"dob": date(1980, 1, 1)})

        assert meta.dob == "1980-01-01"


class TestLoadAccountRecord:
    def test_load_account_record_returns_typed_model(self, tmp_path: Path) -> None:
        owner_dir = tmp_path / "alice"
        owner_dir.mkdir()
        (owner_dir / "ISA.json").write_text(
            json.dumps({"account_type": " ISA ", "currency": " GBP ", "holdings": [{"ticker": "VWRP"}]})
        )

        record = load_account_record("alice", "ISA", data_root=tmp_path)

        assert record.account_type == "ISA"
        assert record.currency == "GBP"
        assert record.holdings == [{"ticker": "VWRP"}]

    def test_invalid_account_record_raises_validation_error(self, tmp_path: Path) -> None:
        owner_dir = tmp_path / "alice"
        owner_dir.mkdir()
        (owner_dir / "ISA.json").write_text(json.dumps({"holdings": "bad"}))

        with pytest.raises(Exception, match="expected list"):
            load_account_record("alice", "ISA", data_root=tmp_path)


class TestMergeAccountsWithOwner:
    def test_merges_without_duplication_and_sets_missing_full_name(self) -> None:
        base = {"owner": "alex", "accounts": ["ISA"]}
        extra = {"accounts": ["isa", "SIPP"], "full_name": "Alex Smith"}

        _merge_accounts(base, extra)

        assert base["accounts"] == ["ISA", "SIPP"]
        assert base["full_name"] == "Alex Smith"


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


class TestResolveDefaultAccountsRoot:
    """Regression coverage for issue #5072: valid owners 404'd on /performance,
    /var and portfolio-group endpoints whenever ``config.accounts_root`` pointed
    at a directory that doesn't exist in the current environment, because
    ``load_account``/``load_person_metadata``/``user_config``/``approvals``
    resolved that root directly with no fallback (unlike ``list_plots`` and
    ``resolve_accounts_root``, which already degrade to the repo-local
    ``data/accounts`` tree)."""

    def _patch_paths(self, monkeypatch, tmp_path, primary, fallback):
        def fake_resolve_paths(repo_root, accounts_root):
            if repo_root is None and accounts_root is None:
                return ResolvedPaths(tmp_path, fallback, fallback.parent / "virtual_portfolios")
            return ResolvedPaths(tmp_path, primary, primary.parent / "virtual_portfolios")

        monkeypatch.setattr(data_loader, "resolve_paths", fake_resolve_paths)
        monkeypatch.setattr(
            data_loader,
            "config",
            type("Cfg", (), {"repo_root": tmp_path, "accounts_root": primary})(),
        )

    def test_falls_back_when_configured_root_missing(self, tmp_path, monkeypatch):
        primary = tmp_path / "missing_primary"
        fallback = tmp_path / "fallback"
        fallback.mkdir()
        self._patch_paths(monkeypatch, tmp_path, primary, fallback)

        assert resolve_default_accounts_root() == fallback

    def test_uses_configured_root_when_it_exists(self, tmp_path, monkeypatch):
        primary = tmp_path / "primary"
        primary.mkdir()
        fallback = tmp_path / "fallback"
        fallback.mkdir()
        self._patch_paths(monkeypatch, tmp_path, primary, fallback)

        assert resolve_default_accounts_root() == primary

    def test_returns_primary_when_neither_root_exists(self, tmp_path, monkeypatch):
        """Neither root exists on disk (e.g. a fresh checkout with no data/
        directory at all). There's nothing sensible to fall back to, so this
        degrades to the pre-fallback behaviour: return the (non-existent)
        configured root and let callers raise FileNotFoundError/MissingData
        when they try to actually read from it."""
        primary = tmp_path / "missing_primary"
        fallback = tmp_path / "missing_fallback"
        self._patch_paths(monkeypatch, tmp_path, primary, fallback)

        assert resolve_default_accounts_root() == primary
        assert not resolve_default_accounts_root().exists()

        with pytest.raises(FileNotFoundError):
            resolve_owner_dir("alice")


class TestResolveOwnerDir:
    def test_finds_owner_under_fallback_root(self, tmp_path, monkeypatch):
        primary = tmp_path / "missing_primary"
        fallback = tmp_path / "fallback"
        owner_dir = fallback / "alice"
        owner_dir.mkdir(parents=True)
        TestResolveDefaultAccountsRoot()._patch_paths(monkeypatch, tmp_path, primary, fallback)

        assert resolve_owner_dir("alice") == owner_dir

    def test_raises_when_owner_missing_everywhere(self, tmp_path, monkeypatch):
        primary = tmp_path / "missing_primary"
        fallback = tmp_path / "fallback"
        fallback.mkdir()
        TestResolveDefaultAccountsRoot()._patch_paths(monkeypatch, tmp_path, primary, fallback)

        with pytest.raises(FileNotFoundError):
            resolve_owner_dir("nobody")

    def test_explicit_accounts_root_bypasses_fallback(self, tmp_path):
        owner_dir = tmp_path / "explicit" / "alice"
        owner_dir.mkdir(parents=True)

        assert resolve_owner_dir("alice", tmp_path / "explicit") == owner_dir


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
    def _configure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        repo_root: Path,
        accounts_root: Path,
        disable_auth: bool | None,
    ) -> None:
        cfg = Config()
        cfg.repo_root = repo_root
        cfg.accounts_root = accounts_root
        cfg.disable_auth = disable_auth
        cfg.app_env = None
        monkeypatch.setattr("backend.common.data_loader.config", cfg)
        monkeypatch.delenv(DATA_BUCKET_ENV, raising=False)

    def test_authentication_required_skips_special_accounts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        assert all("full_name" not in entry for entry in result)

    def test_respects_viewers_when_auth_disabled_and_user_provided(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=True)

        _write_owner(data_root, "alice", ["alpha"], viewers=["viewer"])
        _write_owner(data_root, "demo", ["demo1"], viewers=[])

        result = _list_local_plots(data_root=data_root, current_user="viewer")

        assert result == [
            {"owner": "alice", "accounts": ["alpha"]},
        ]
        assert all("full_name" not in entry for entry in result)

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
        assert all("full_name" not in entry for entry in result)

    def test_includes_full_name_from_metadata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=True)

        _write_owner(
            data_root,
            "carol",
            ["gamma"],
            viewers=[],
            full_name="Carol Example",
        )

        result = _list_local_plots(data_root=data_root, current_user=None)

        assert result == [
            {"owner": "carol", "full_name": "Carol Example", "accounts": ["gamma"]},
        ]

    def test_skips_metadata_and_transaction_exports(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=True)

        _write_owner(data_root, "charlie", ["isa", "brokerage"])
        owner_dir = data_root / "charlie"
        for filename in [
            "person.json",
            "config.json",
            "notes.json",
            "settings.json",
            "approvals.json",
            "approval_requests.json",
            "isa_transactions.json",
            "BROKERAGE_TRANSACTIONS.json",
        ]:
            (owner_dir / filename).write_text("{}")

        result = _list_local_plots(data_root=data_root, current_user=None)

        assert result == [
            {
                "owner": "charlie",
                "accounts": ["brokerage", "isa"],
            },
        ]
        assert all("full_name" not in entry for entry in result)

    def test_authentication_disabled_allows_anonymous_access(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=True)

        _write_owner(data_root, "demo", ["demo1"], viewers=[])
        _write_owner(data_root, "carol", ["gamma"], viewers=["other"])

        result = _list_local_plots(data_root=data_root, current_user=None)

        assert result == [
            {"owner": "carol", "accounts": ["gamma"]},
        ]
        assert all(entry["owner"] not in {"demo", ".idea"} for entry in result)

    @pytest.mark.xfail(reason="To fix")
    def test_overridden_demo_identity_hides_default_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_root = tmp_path / "accounts"
        self._configure(monkeypatch, tmp_path, data_root, disable_auth=True)

        data_loader.config.demo_identity = "steve"

        _write_owner(data_root, "demo", ["demo1"], viewers=[])
        _write_owner(data_root, "steve", ["growth"], viewers=[])

        result = _list_local_plots(data_root=data_root, current_user=None)

        assert result == []



    def test_falls_back_to_repository_when_primary_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo_root = tmp_path / "repo"
        primary_accounts = repo_root / "accounts"
        fallback_accounts = tmp_path / "fallback" / "accounts"
        primary_accounts.mkdir(parents=True, exist_ok=True)
        fallback_accounts.mkdir(parents=True, exist_ok=True)
        self._configure(monkeypatch, repo_root, primary_accounts, disable_auth=True)

        _write_owner(fallback_accounts, "eve", ["gia"], viewers=[])

        calls = {"count": 0}

        def fake_resolve_paths(repo_root_value, accounts_root_value):
            calls["count"] += 1
            if calls["count"] == 1:
                return ResolvedPaths(repo_root, primary_accounts, repo_root / "virtual")
            return ResolvedPaths(Path("fallback-repo"), fallback_accounts, Path("fallback-repo") / "virtual")

        monkeypatch.setattr("backend.common.data_loader.resolve_paths", fake_resolve_paths)

        result = _list_local_plots(current_user=None)

        assert result == [
            {"owner": "eve", "accounts": ["gia"]},
        ]

    def test_explicit_root_does_not_merge_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo_root = tmp_path / "repo"
        primary_accounts = repo_root / "accounts"
        fallback_accounts = tmp_path / "fallback" / "accounts"
        primary_accounts.mkdir(parents=True, exist_ok=True)
        fallback_accounts.mkdir(parents=True, exist_ok=True)
        self._configure(monkeypatch, repo_root, primary_accounts, disable_auth=True)

        explicit_root = tmp_path / "custom"
        explicit_root.mkdir()
        _write_owner(explicit_root, "zoe", ["isa"], viewers=[])
        _write_owner(fallback_accounts, "eve", ["gia"], viewers=[])

        calls = {"count": 0}

        def fake_resolve_paths(repo_root_value, accounts_root_value):
            calls["count"] += 1
            if calls["count"] == 1:
                return ResolvedPaths(repo_root, primary_accounts, repo_root / "virtual")
            return ResolvedPaths(Path("fallback-repo"), fallback_accounts, Path("fallback-repo") / "virtual")

        monkeypatch.setattr("backend.common.data_loader.resolve_paths", fake_resolve_paths)

        result = _list_local_plots(data_root=explicit_root, current_user=None)

        assert result == [
            {"owner": "zoe", "accounts": ["isa"]},
        ]

    def test_list_plots_with_explicit_root_skips_demo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo_root = tmp_path / "repo"
        accounts_root = repo_root / "accounts"
        accounts_root.mkdir(parents=True, exist_ok=True)
        self._configure(monkeypatch, repo_root, accounts_root, disable_auth=True)

        explicit_root = tmp_path / "custom_accounts"
        _write_owner(explicit_root, "demo", ["demo1"], viewers=[])
        _write_owner(explicit_root, "carol", ["gamma"], viewers=[])

        result = list_plots(data_root=explicit_root, current_user=None)

        assert result == [
            OwnerSummaryRecord(owner="carol", accounts=["gamma"]),
        ]
        assert all(entry.full_name is None for entry in result)
        assert all(entry.owner not in {"demo", ".idea"} for entry in result)

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
            {
                "owner": "alice",
                "accounts": ["alpha"],
                "email": "alice@example.com",
            },
        ]


class TestLocalOwnerIndexCache:
    def test_safe_file_signature_reuses_digest_when_stat_is_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        person_path = tmp_path / "person.json"
        person_path.write_text(json.dumps({"full_name": "Alice", "viewers": []}))
        mtime_ns, size, digest = data_loader._safe_file_signature(person_path)

        def fail_open(self: Path, *args: object, **kwargs: object) -> object:
            raise AssertionError("unchanged signatures should not reopen the file")

        monkeypatch.setattr(Path, "open", fail_open)

        assert data_loader._safe_file_signature(person_path, digest, mtime_ns, size) == (
            mtime_ns,
            size,
            digest,
        )

    def test_reuses_cached_owner_index_when_signature_is_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_root = tmp_path / "accounts"
        data_root.mkdir()
        _write_owner(data_root, "alice", ["isa"], viewers=[], full_name="Alice Example")

        build_calls = {"count": 0}
        original_build = data_loader._build_local_owner_index

        def counting_build(root: Path, signature=None):
            build_calls["count"] += 1
            return original_build(root, signature)

        monkeypatch.setattr(data_loader, "_build_local_owner_index", counting_build)

        first = _list_local_plots(data_root=data_root, current_user=None)
        second = _list_local_plots(data_root=data_root, current_user=None)

        assert first == second == [
            {"owner": "alice", "accounts": ["isa"], "full_name": "Alice Example"},
        ]
        assert build_calls["count"] == 1

    def test_invalidates_cached_owner_index_when_metadata_changes(
        self, tmp_path: Path
    ) -> None:
        data_root = tmp_path / "accounts"
        data_root.mkdir()
        _write_owner(data_root, "alice", ["isa"], viewers=[], full_name="Alice One")

        first = _list_local_plots(data_root=data_root, current_user=None)
        assert first[0]["full_name"] == "Alice One"

        person_path = data_root / "alice" / "person.json"
        person_path.write_text(json.dumps({"full_name": "Alice Updated", "viewers": []}))

        second = _list_local_plots(data_root=data_root, current_user=None)
        meta = load_person_meta("alice", data_root=data_root)

        assert second[0]["full_name"] == "Alice Updated"
        assert meta["full_name"] == "Alice Updated"

    def test_invalidates_cached_owner_index_when_accounts_change(
        self, tmp_path: Path
    ) -> None:
        data_root = tmp_path / "accounts"
        data_root.mkdir()
        _write_owner(data_root, "alice", ["isa"], viewers=[])

        first = _list_local_plots(data_root=data_root, current_user=None)
        assert first == [{"owner": "alice", "accounts": ["isa"]}]

        (data_root / "alice" / "gia.json").write_text("{}")

        second = _list_local_plots(data_root=data_root, current_user=None)

        assert second == [{"owner": "alice", "accounts": ["gia", "isa"]}]

    def test_invalidates_cached_owner_index_when_owner_added(
        self, tmp_path: Path
    ) -> None:
        data_root = tmp_path / "accounts"
        data_root.mkdir()
        _write_owner(data_root, "alice", ["isa"], viewers=[])

        first = _list_local_plots(data_root=data_root, current_user=None)
        assert [e["owner"] for e in first] == ["alice"]

        _write_owner(data_root, "bob", ["sipp"], viewers=[])

        second = _list_local_plots(data_root=data_root, current_user=None)
        assert [e["owner"] for e in second] == ["alice", "bob"]

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "st_ctime_ns is file creation time on Windows; "
            "content-only changes cannot be detected without re-reading"
        ),
    )
    def test_invalidates_cached_owner_index_when_content_changes_without_stat_change(
        self, tmp_path: Path
    ) -> None:
        data_root = tmp_path / "accounts"
        data_root.mkdir()
        _write_owner(data_root, "alice", ["isa"], viewers=[], full_name="Alice One")

        first = _list_local_plots(data_root=data_root, current_user=None)
        assert first[0]["full_name"] == "Alice One"

        person_path = data_root / "alice" / "person.json"
        original_stat = person_path.stat()
        replacement = json.dumps({"full_name": "Alice Two", "viewers": []})
        # Use byte-length to match st_size correctly (avoids multi-byte char surprises).
        assert len(replacement.encode()) == original_stat.st_size

        # Write bytes directly so size is unchanged, then restore mtime/atime.
        # ctime updates to "now" on POSIX, which is what triggers re-hashing.
        # Fast filesystems can report the same ctime when the rewrite happens in
        # the same clock tick as the original write, so retry briefly until the
        # test has a real ctime-only signature change to exercise.
        deadline = time.monotonic() + 1
        updated_stat = original_stat
        while time.monotonic() < deadline:
            person_path.write_bytes(replacement.encode())
            os.utime(person_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            updated_stat = person_path.stat()
            if updated_stat.st_ctime_ns != original_stat.st_ctime_ns:
                break
            time.sleep(0.001)
        assert updated_stat.st_ctime_ns != original_stat.st_ctime_ns

        second = _list_local_plots(data_root=data_root, current_user=None)

        assert second[0]["full_name"] == "Alice Two"


class TestLoadDemoOwner:
    def test_returns_demo_summary_when_available(
        self, tmp_path: Path
    ) -> None:
        demo_root = tmp_path / "data"
        demo_dir = demo_root / "demo"
        demo_dir.mkdir(parents=True)
        (demo_dir / "isa.json").write_text("{}")

        (demo_dir / "person.json").write_text(json.dumps({"full_name": "Demo User", "viewers": []}))

        result = _load_demo_owner(demo_root)

        assert result == {
            "owner": "demo",
            "accounts": ["isa"],
            "full_name": "Demo User",
        }

    def test_returns_none_when_demo_directory_missing(self, tmp_path: Path) -> None:
        result = _load_demo_owner(tmp_path)

        assert result is None


def test_list_aws_plots_enforces_email_and_viewer_permissions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = Config()
    cfg.app_env = "aws"
    cfg.disable_auth = False
    cfg.repo_root = tmp_path
    cfg.accounts_root = tmp_path / "accounts"
    monkeypatch.setattr("backend.common.data_loader.config", cfg)

    class _FakeS3DataProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def list_plots(self, current_user=None):
            return [
                {"owner": "alice", "accounts": ["isa"]},
                {"owner": "bob", "accounts": ["gia"]},
            ]

    meta_by_owner = {
        "alice": {"email": "Alice@Example.com", "viewers": []},
        "bob": {"email": "bob@example.com", "viewers": []},
    }

    monkeypatch.setattr("backend.common.data_loader.S3DataProvider", _FakeS3DataProvider)
    monkeypatch.setattr(
        "backend.common.data_loader.load_person_meta",
        lambda owner, root=None: meta_by_owner[owner],
    )

    result = data_loader._list_aws_plots(current_user="alice@example.com")

    assert [entry["owner"] for entry in result] == ["alice"]


def test_list_plots_prefers_aws_results(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = Config()
    cfg.app_env = "aws"
    cfg.disable_auth = True
    cfg.repo_root = tmp_path
    cfg.accounts_root = tmp_path / "accounts"
    monkeypatch.setattr("backend.common.data_loader.config", cfg)
    monkeypatch.delenv(DATA_BUCKET_ENV, raising=False)

    expected = [{"owner": "aws", "full_name": "aws", "accounts": ["isa"]}]

    monkeypatch.setattr(
        "backend.common.data_loader._list_aws_plots",
        lambda current_user=None: expected,
    )
    # Ensure local discovery would be different to verify the AWS path wins.
    monkeypatch.setattr(
        "backend.common.data_loader._list_local_plots",
        lambda data_root, current_user=None: [{"owner": "local", "full_name": "local", "accounts": []}],
    )

    result = list_plots(data_root=None, current_user="user@example.com")

    assert result == [OwnerSummaryRecord.model_validate(entry) for entry in expected]


def test_list_plots_aws_falls_back_to_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = Config()
    cfg.app_env = "aws"
    cfg.disable_auth = True
    cfg.repo_root = tmp_path
    cfg.accounts_root = tmp_path / "accounts"
    monkeypatch.setattr("backend.common.data_loader.config", cfg)
    monkeypatch.delenv(DATA_BUCKET_ENV, raising=False)

    monkeypatch.setattr(
        "backend.common.data_loader._list_aws_plots",
        lambda current_user=None: [],
    )

    captured: dict[str, tuple[Path | None, object]] = {}

    def fake_local(data_root: Path | None, current_user=None):
        captured["call"] = (data_root, current_user)
        return [{"owner": "local", "full_name": "local", "accounts": ["isa"]}]

    monkeypatch.setattr("backend.common.data_loader._list_local_plots", fake_local)

    result = list_plots(data_root=tmp_path, current_user="viewer")

    assert result == [OwnerSummaryRecord(owner="local", full_name="local", accounts=["isa"])]
    assert captured["call"] == (tmp_path, "viewer")


def test_list_plots_skips_invalid_entries_without_failing_whole_batch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A single malformed owner entry must not take down the whole listing."""

    cfg = Config()
    cfg.app_env = "local"
    cfg.disable_auth = True
    cfg.repo_root = tmp_path
    cfg.accounts_root = tmp_path / "accounts"
    monkeypatch.setattr("backend.common.data_loader.config", cfg)

    monkeypatch.setattr(
        "backend.common.data_loader._list_local_plots",
        lambda data_root, current_user=None: [
            {"owner": "carol", "accounts": ["gamma"]},
            {"owner": None},
            {},
        ],
    )

    with caplog.at_level("WARNING", logger="backend.common.data_loader"):
        result = list_plots(data_root=tmp_path, current_user=None)

    assert result == [OwnerSummaryRecord(owner="carol", accounts=["gamma"])]
    assert "data_loader.list_plots_invalid_entry" in caplog.text


# ---------------------------------------------------------------------------
# data_loader.load_account — path traversal rejection
# ---------------------------------------------------------------------------


def test_load_account_dotdot_owner_raises_missing_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_account must raise MissingData for traversal in owner.

    safe_join catches the traversal and re-raises as MissingData so callers
    see a FileNotFoundError subclass — not ValueError and not a raw open().
    """
    from backend.common.data_loader import load_account
    from backend.common.data_providers import MissingData

    cfg = data_loader.config.__class__()
    cfg.app_env = "local"
    monkeypatch.setattr("backend.common.data_loader.config", cfg)
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    # MissingData specifically — not the broader FileNotFoundError — because the
    # fix guarantees safe_join's ValueError is wrapped before any filesystem access.
    with pytest.raises(MissingData):
        load_account("../evil", "isa", data_root=tmp_path)


def test_load_account_dotdot_account_raises_missing_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_account must raise MissingData for traversal in account."""
    from backend.common.data_loader import load_account
    from backend.common.data_providers import MissingData

    cfg = data_loader.config.__class__()
    cfg.app_env = "local"
    monkeypatch.setattr("backend.common.data_loader.config", cfg)
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()

    with pytest.raises(MissingData):
        load_account("alice", "../../etc/passwd", data_root=tmp_path)
