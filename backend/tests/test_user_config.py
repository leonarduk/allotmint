import json

from backend.common.user_config import load_user_config


def test_load_user_config(tmp_path):
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
    cfg = load_user_config("alice", tmp_path)
    assert cfg.hold_days_min == 5
    assert cfg.max_trades_per_month == 3
    assert cfg.approval_exempt_tickers == ["ABC"]
