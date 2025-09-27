import types

import pytest
from fastapi import FastAPI, HTTPException

from backend.routes import compliance as compliance_module


class PayloadRequest:
    """Lightweight request object with a configurable JSON payload."""

    def __init__(self, payload):
        self.app = FastAPI()
        self._payload = payload

    async def json(self):
        return self._payload


@pytest.fixture
def fastapi_request():
    app = FastAPI()
    request = types.SimpleNamespace(app=app)
    return app, request


def test_known_owners_aggregates_plot_metadata(tmp_path, monkeypatch):
    expected_root = tmp_path / "accounts"

    monkeypatch.setattr(
        compliance_module.data_loader,
        "list_plots",
        lambda root: [
            {"owner": "Alice"},
            {"owner": "Bob"},
            {"owner": "ALICE"},
            {"owner": None},
            {},
        ],
    )
    monkeypatch.setattr(
        compliance_module.data_loader,
        "resolve_paths",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("unused")),
    )

    owners = compliance_module._known_owners(expected_root)

    assert owners == {"alice", "bob"}


def test_known_owners_falls_back_to_directory_iteration(tmp_path, monkeypatch):
    accounts_root = tmp_path / "owners"
    accounts_root.mkdir()
    (accounts_root / "Alice").mkdir()
    (accounts_root / "beta").mkdir()
    (accounts_root / "notes.txt").write_text("ignore")

    def raise_failure(_):
        raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(
        compliance_module.data_loader,
        "list_plots",
        raise_failure,
    )
    monkeypatch.setattr(
        compliance_module.data_loader,
        "resolve_paths",
        lambda *_, **__: types.SimpleNamespace(
            accounts_root=tmp_path / "no_demo"
        ),
    )

    owners = compliance_module._known_owners(accounts_root)

    assert owners == {"alice", "beta"}


def test_known_owners_adds_demo_owner_when_available(tmp_path, monkeypatch):
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()
    (accounts_root / "Alice").mkdir()

    fallback_root = tmp_path / "fallback"
    fallback_root.mkdir()
    (fallback_root / "demo").mkdir()

    monkeypatch.setattr(
        compliance_module.data_loader,
        "list_plots",
        lambda _: [{"owner": "Alice"}],
    )
    monkeypatch.setattr(
        compliance_module.data_loader,
        "resolve_paths",
        lambda *_, **__: types.SimpleNamespace(accounts_root=fallback_root),
    )

    owners = compliance_module._known_owners(accounts_root)

    assert owners == {"alice", "demo"}


@pytest.mark.anyio
async def test_compliance_for_owner_missing_directory(tmp_path, monkeypatch, fastapi_request):
    app, request = fastapi_request
    accounts_root = tmp_path / "accounts"

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req: accounts_root,
    )
    monkeypatch.setattr(
        compliance_module,
        "resolve_owner_directory",
        lambda root, owner: None,
    )

    with pytest.raises(HTTPException) as excinfo:
        await compliance_module.compliance_for_owner("alice", request)

    assert excinfo.value.status_code == 404


@pytest.mark.anyio
async def test_compliance_for_owner_rejects_unknown_owner(tmp_path, monkeypatch, fastapi_request):
    app, request = fastapi_request
    accounts_root = tmp_path / "accounts"
    owner_dir = tmp_path / "accounts" / "Alice"

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req: accounts_root,
    )
    monkeypatch.setattr(
        compliance_module,
        "resolve_owner_directory",
        lambda root, owner: owner_dir,
    )
    monkeypatch.setattr(
        compliance_module,
        "_known_owners",
        lambda root: {"bob"},
    )

    with pytest.raises(HTTPException) as excinfo:
        await compliance_module.compliance_for_owner("alice", request)

    assert excinfo.value.status_code == 404


@pytest.mark.anyio
async def test_compliance_for_owner_translates_missing_files(tmp_path, monkeypatch, fastapi_request):
    app, request = fastapi_request
    accounts_root = tmp_path / "accounts"
    owner_dir = accounts_root / "Alice"

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req: accounts_root,
    )
    monkeypatch.setattr(
        compliance_module,
        "resolve_owner_directory",
        lambda root, owner: owner_dir,
    )
    monkeypatch.setattr(
        compliance_module,
        "_known_owners",
        lambda root: {"alice"},
    )

    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(
        compliance_module.compliance,
        "check_owner",
        raise_missing,
    )

    with pytest.raises(HTTPException) as excinfo:
        await compliance_module.compliance_for_owner("alice", request)

    assert excinfo.value.status_code == 404


@pytest.mark.anyio
async def test_validate_trade_requires_owner(tmp_path, monkeypatch):
    request = PayloadRequest({})

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req, allow_missing=False: tmp_path,
    )

    with pytest.raises(HTTPException) as excinfo:
        await compliance_module.validate_trade(request)

    assert excinfo.value.status_code == 422


@pytest.mark.anyio
async def test_validate_trade_rejects_blank_owner(tmp_path, monkeypatch):
    request = PayloadRequest({"owner": "   "})

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req, allow_missing=False: tmp_path,
    )

    with pytest.raises(HTTPException) as excinfo:
        await compliance_module.validate_trade(request)

    assert excinfo.value.status_code == 404


@pytest.mark.anyio
async def test_validate_trade_rejects_disallowed_owner(tmp_path, monkeypatch):
    request = PayloadRequest({"owner": "alice"})
    accounts_root = tmp_path / "accounts"

    owner_dir = accounts_root / "Alice"

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req, allow_missing=False: accounts_root,
    )
    monkeypatch.setattr(
        compliance_module,
        "resolve_owner_directory",
        lambda root, owner: owner_dir,
    )
    monkeypatch.setattr(
        compliance_module,
        "_known_owners",
        lambda root: {"bob"},
    )

    with pytest.raises(HTTPException) as excinfo:
        await compliance_module.validate_trade(request)

    assert excinfo.value.status_code == 404


@pytest.mark.anyio
async def test_validate_trade_requires_known_directory_when_present(tmp_path, monkeypatch):
    request = PayloadRequest({"owner": "alice"})

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req, allow_missing=False: tmp_path,
    )
    monkeypatch.setattr(
        compliance_module,
        "resolve_owner_directory",
        lambda root, owner: None,
    )
    monkeypatch.setattr(
        compliance_module,
        "_known_owners",
        lambda root: {"alice"},
    )

    with pytest.raises(HTTPException) as excinfo:
        await compliance_module.validate_trade(request)

    assert excinfo.value.status_code == 404


@pytest.mark.anyio
async def test_validate_trade_normalises_owner_name(tmp_path, monkeypatch):
    request = PayloadRequest({"owner": "  alice  "})
    accounts_root = tmp_path / "accounts"
    canonical_dir = accounts_root / "ALICE"

    captured = {}

    def fake_check_trade(trade, root, *, scaffold_missing):
        captured["trade"] = dict(trade)
        captured["root"] = root
        captured["scaffold_missing"] = scaffold_missing
        return {"status": "ok"}

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req, allow_missing=False: accounts_root,
    )
    monkeypatch.setattr(
        compliance_module,
        "resolve_owner_directory",
        lambda root, owner: canonical_dir,
    )
    monkeypatch.setattr(
        compliance_module,
        "_known_owners",
        lambda root: {"alice"},
    )
    monkeypatch.setattr(
        compliance_module.compliance,
        "check_trade",
        fake_check_trade,
    )

    result = await compliance_module.validate_trade(request)

    assert result == {"status": "ok"}
    assert captured["trade"]["owner"] == "ALICE"
    assert captured["root"] is accounts_root
    assert captured["scaffold_missing"] is False


@pytest.mark.anyio
async def test_validate_trade_translates_value_error(tmp_path, monkeypatch):
    request = PayloadRequest({"owner": "alice"})
    accounts_root = tmp_path / "accounts"
    canonical_dir = accounts_root / "ALICE"

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req, allow_missing=False: accounts_root,
    )
    monkeypatch.setattr(
        compliance_module,
        "resolve_owner_directory",
        lambda root, owner: canonical_dir,
    )
    monkeypatch.setattr(
        compliance_module,
        "_known_owners",
        lambda root: {"alice"},
    )

    def raise_value_error(*args, **kwargs):
        raise ValueError("invalid")

    monkeypatch.setattr(
        compliance_module.compliance,
        "check_trade",
        raise_value_error,
    )

    with pytest.raises(HTTPException) as excinfo:
        await compliance_module.validate_trade(request)

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail == "invalid"


@pytest.mark.anyio
async def test_validate_trade_scaffolds_missing_directory(tmp_path, monkeypatch, caplog):
    request = PayloadRequest({"owner": "alice"})
    accounts_root = tmp_path / "accounts"

    recorded = {}

    def fake_check_trade(trade, root, *, scaffold_missing):
        recorded["trade"] = dict(trade)
        recorded["scaffold_missing"] = scaffold_missing
        return {"result": "ok"}

    def failing_scaffold(owner, root):
        recorded["scaffold_args"] = (owner, root)
        raise RuntimeError("boom")

    monkeypatch.setattr(
        compliance_module,
        "resolve_accounts_root",
        lambda req, allow_missing=False: accounts_root,
    )
    monkeypatch.setattr(
        compliance_module,
        "resolve_owner_directory",
        lambda root, owner: None,
    )
    monkeypatch.setattr(
        compliance_module,
        "_known_owners",
        lambda root: set(),
    )
    monkeypatch.setattr(
        compliance_module.compliance,
        "check_trade",
        fake_check_trade,
    )
    monkeypatch.setattr(
        compliance_module.compliance,
        "ensure_owner_scaffold",
        failing_scaffold,
    )

    caplog.set_level("WARNING")

    result = await compliance_module.validate_trade(request)

    assert result == {"result": "ok"}
    assert recorded["trade"]["owner"] == "alice"
    assert recorded["scaffold_missing"] is True
    assert recorded["scaffold_args"] == ("alice", accounts_root)
    assert any("failed to scaffold compliance data" in record.message for record in caplog.records)
