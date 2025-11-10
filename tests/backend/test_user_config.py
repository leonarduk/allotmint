import json
from types import SimpleNamespace

import pytest

from backend.common import user_config as uc


def _patch_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(
        uc,
        "resolve_paths",
        lambda repo_root, accounts_root: SimpleNamespace(accounts_root=tmp_path),
    )
    monkeypatch.setattr(
        uc,
        "config",
        SimpleNamespace(
            repo_root=tmp_path,
            accounts_root=tmp_path,
            hold_days_min=1,
            max_trades_per_month=2,
            approval_exempt_types=["T"],
            approval_exempt_tickers=["XYZ"],
        ),
    )


def test_load_user_config(tmp_path, monkeypatch):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "settings.json").write_text(
        json.dumps(
            {
                "hold_days_min": 5,
                "max_trades_per_month": 3,
                "approval_exempt_tickers": ["ABC"],
            }
        )
    )
    cfg = uc.load_user_config("alice", tmp_path)
    assert cfg.hold_days_min == 5
    assert cfg.max_trades_per_month == 3
    assert cfg.approval_exempt_tickers == ["ABC"]


def test_parse_str_list():
    assert uc._parse_str_list(["a", "", None]) == ["a"]
    assert uc._parse_str_list("a, b ,") == ["a", "b"]
    assert uc._parse_str_list(123) is None


def test_settings_path_missing(tmp_path, monkeypatch):
    _patch_defaults(monkeypatch, tmp_path)
    with pytest.raises(FileNotFoundError):
        uc._settings_path("missing", tmp_path)


def test_load_defaults_on_invalid_json(tmp_path, monkeypatch):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "bob"
    owner_dir.mkdir()
    (owner_dir / "settings.json").write_text("{bad json")
    cfg = uc.load_user_config("bob", tmp_path)
    assert cfg.hold_days_min == 1
    assert cfg.approval_exempt_types == ["T"]
    assert cfg.approval_exempt_tickers == ["XYZ"]


def test_save_user_config_merges(tmp_path, monkeypatch):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "carol"
    owner_dir.mkdir()
    path = owner_dir / "settings.json"
    path.write_text(json.dumps({"unknown": 1, "hold_days_min": 5}))
    uc.save_user_config(
        "carol",
        {"hold_days_min": 10, "max_trades_per_month": 3, "unknown": 9},
        tmp_path,
    )
    data = json.loads(path.read_text())
    assert data["hold_days_min"] == 10
    assert data["max_trades_per_month"] == 3
    assert data["unknown"] == 1
