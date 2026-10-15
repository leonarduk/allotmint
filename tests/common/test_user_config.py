import json
from types import SimpleNamespace

import pytest

from backend.common import user_config as uc


def _patch_defaults(monkeypatch, tmp_path):
    """Patch config to point at a temporary directory."""
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


def test_settings_path_missing(tmp_path, monkeypatch):
    _patch_defaults(monkeypatch, tmp_path)
    with pytest.raises(FileNotFoundError):
        uc.settings_path("missing", tmp_path)


@pytest.mark.parametrize("contents", [None, "{bad json"])
def test_load_user_config_defaults(tmp_path, monkeypatch, contents):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    if contents is not None:
        (owner_dir / "settings.json").write_text(contents)
    cfg = uc.load_user_config("alice", tmp_path)
    assert cfg.hold_days_min == 1
    assert cfg.max_trades_per_month == 2
    assert cfg.approval_exempt_types == ["T"]
    assert cfg.approval_exempt_tickers == ["XYZ"]


def test_save_user_config_merges(tmp_path, monkeypatch):
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "bob"
    owner_dir.mkdir()
    path = owner_dir / "settings.json"
    path.write_text(json.dumps({"unknown": 1, "hold_days_min": 5}))
    uc.save_user_config(
        "bob",
        {"hold_days_min": 10, "max_trades_per_month": 3, "unknown": 9},
        tmp_path,
    )
    data = json.loads(path.read_text())
    assert data["hold_days_min"] == 10
    assert data["max_trades_per_month"] == 3
    assert data["unknown"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("hold_days_min", -3),
        ("max_trades_per_month", -5),
        ("hold_days_min", 1.5),
        ("max_trades_per_month", "7"),
        ("hold_days_min", True),
    ],
)
def test_save_user_config_rejects_invalid_trading_limits(tmp_path, monkeypatch, field, value):
    # #10916: a negative limit used to be written straight to settings.json.
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "dave"
    owner_dir.mkdir()
    path = owner_dir / "settings.json"
    original = json.dumps({field: 4})
    path.write_text(original)
    with pytest.raises(uc.InvalidUserConfigError, match=field):
        uc.save_user_config("dave", {field: value}, tmp_path)
    assert path.read_text() == original


def test_save_user_config_rejects_negative_limit_from_dataclass(tmp_path, monkeypatch):
    _patch_defaults(monkeypatch, tmp_path)
    (tmp_path / "erin").mkdir()
    with pytest.raises(uc.InvalidUserConfigError):
        uc.save_user_config("erin", uc.UserConfig(max_trades_per_month=-1), tmp_path)


def test_save_user_config_accepts_zero_and_none_limits(tmp_path, monkeypatch):
    # Zero is a valid limit; None/blank still means "use the default" and
    # leaves the stored value untouched.
    _patch_defaults(monkeypatch, tmp_path)
    owner_dir = tmp_path / "fran"
    owner_dir.mkdir()
    path = owner_dir / "settings.json"
    path.write_text(json.dumps({"max_trades_per_month": 4}))
    uc.save_user_config("fran", {"hold_days_min": 0, "max_trades_per_month": None}, tmp_path)
    data = json.loads(path.read_text())
    assert data["hold_days_min"] == 0
    assert data["max_trades_per_month"] == 4
