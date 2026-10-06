import json
from types import SimpleNamespace

import pytest

from backend.common import user_config as uc


def _patch_defaults(monkeypatch, tmp_path):
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
        uc.settings_path("missing", tmp_path)


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


# --- #9514: never overwrite an unreadable settings.json -----------------------


def test_save_refuses_to_overwrite_unreadable_settings(tmp_path, monkeypatch):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "dave"
    owner_dir.mkdir()
    path = owner_dir / "settings.json"
    corrupt = '{"hold_days_min": 30, "allocation_policy": {"targets": {"equity": 100}},'
    path.write_text(corrupt)

    with pytest.raises(uc.SettingsUnreadableError):
        uc.save_user_config("dave", {"max_trades_per_month": 5}, tmp_path)
    assert path.read_text() == corrupt


@pytest.mark.parametrize("content", ["[1, 2]", '"text"'])
def test_save_refuses_non_object_settings(tmp_path, monkeypatch, content):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "erin"
    owner_dir.mkdir()
    path = owner_dir / "settings.json"
    path.write_text(content)

    with pytest.raises(uc.SettingsUnreadableError):
        uc.save_user_config("erin", {"max_trades_per_month": 5}, tmp_path)
    assert path.read_text() == content


@pytest.mark.parametrize("content", ["", "  \n", "null"])
def test_save_over_empty_or_null_settings_writes_normally(tmp_path, monkeypatch, content):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "fay"
    owner_dir.mkdir()
    path = owner_dir / "settings.json"
    path.write_text(content)

    uc.save_user_config("fay", {"max_trades_per_month": 5}, tmp_path)
    assert json.loads(path.read_text()) == {"max_trades_per_month": 5}


def test_save_preserves_other_writers_keys(tmp_path, monkeypatch):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "gus"
    owner_dir.mkdir()
    path = owner_dir / "settings.json"
    policy = {"targets": {"equity": 60.0, "bond": 40.0}, "tolerance_pct": 5.0}
    path.write_text(json.dumps({"hold_days_min": 30, "allocation_policy": policy}))

    uc.save_user_config("gus", {"max_trades_per_month": 5}, tmp_path)
    data = json.loads(path.read_text())
    assert data["allocation_policy"] == policy
    assert data["hold_days_min"] == 30
    assert data["max_trades_per_month"] == 5


def test_load_logs_unreadable_settings_and_uses_defaults(tmp_path, monkeypatch, caplog):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "hal"
    owner_dir.mkdir()
    (owner_dir / "settings.json").write_text("{bad json")

    with caplog.at_level("WARNING", logger="backend.common.user_config"):
        cfg = uc.load_user_config("hal", tmp_path)
    assert cfg.hold_days_min == 1
    assert any("Using default user config for hal" in r.getMessage() for r in caplog.records)
