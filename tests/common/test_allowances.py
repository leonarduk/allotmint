import json
import datetime as dt

from backend.common.allowances import (
    current_tax_year,
    load_yearly_contributions,
    remaining_allowances,
)


def test_current_tax_year_transition():
    assert current_tax_year(dt.date(2024, 4, 5)) == "2023-2024"
    assert current_tax_year(dt.date(2024, 4, 6)) == "2024-2025"


def test_load_yearly_contributions_missing_and_invalid(tmp_path):
    # Missing file returns empty mapping
    assert load_yearly_contributions("alice", "2024-2025", root=tmp_path) == {}

    # Invalid JSON returns empty mapping
    allowances_dir = tmp_path / "allowances"
    allowances_dir.mkdir()
    (allowances_dir / "alice.json").write_text("{invalid")
    assert load_yearly_contributions("alice", "2024-2025", root=tmp_path) == {}


def test_load_yearly_contributions_non_numeric(tmp_path):
    allowances_dir = tmp_path / "allowances"
    allowances_dir.mkdir()
    (allowances_dir / "bob.json").write_text(
        json.dumps({"2024-2025": {"ISA": "oops", "pension": 5000, "other": "100"}})
    )
    result = load_yearly_contributions("bob", "2024-2025", root=tmp_path)
    assert result == {"pension": 5000.0, "other": 100.0}


def test_remaining_allowances_clamps_and_custom_limits(tmp_path):
    allowances_dir = tmp_path / "allowances"
    allowances_dir.mkdir()
    (allowances_dir / "carol.json").write_text(
        json.dumps({"2024-2025": {"ISA": 25_000}})
    )

    # Exceeds default ISA limit -> remaining is clamped to zero
    default_res = remaining_allowances("carol", "2024-2025", root=tmp_path)
    assert default_res["ISA"] == {"used": 25_000.0, "limit": 20_000.0, "remaining": 0.0}

    # Custom limit is honoured
    custom_res = remaining_allowances(
        "carol", "2024-2025", limits={"ISA": 30_000}, root=tmp_path
    )
    assert custom_res["ISA"] == {"used": 25_000.0, "limit": 30_000.0, "remaining": 5_000.0}
