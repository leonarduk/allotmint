from __future__ import annotations

from pathlib import Path

import pytest

from scripts.qa.var_payload_validator import validate_var_payload, validate_var_payload_file


def test_check_var_structure_accepts_nested_var_payload() -> None:
    validate_var_payload(
        {
            "owner": "demo",
            "as_of": "2026-03-30",
            "var": {
                "window_days": 365,
                "confidence": 0.95,
                "1d": 123.45,
                "10d": 456.78,
            },
            "sharpe_ratio": 1.23,
        }
    )


def test_check_var_structure_rejects_payload_without_numeric_var() -> None:
    with pytest.raises(ValueError, match="VaR numeric value not found"):
        validate_var_payload(
            {
                "owner": "demo",
                "as_of": "2026-03-30",
                "var": {"window_days": 365, "confidence": 0.95},
                "sharpe_ratio": 1.23,
            }
        )


def test_check_var_structure_accepts_alternative_horizon_key() -> None:
    validate_var_payload(
        {
            "owner": "demo",
            "as_of": "2026-03-30",
            "var": {"window_days": 365, "confidence": 0.95, "30d": 987.65},
            "sharpe_ratio": 1.23,
        }
    )


def test_check_var_structure_accepts_legacy_flat_var_value() -> None:
    validate_var_payload(
        {
            "owner": "demo",
            "as_of": "2026-03-30",
            "var": 150.0,
            "sharpe_ratio": 1.23,
        }
    )


def test_check_var_structure_rejects_non_horizon_numeric_nested_key() -> None:
    with pytest.raises(ValueError, match="VaR numeric value not found"):
        validate_var_payload(
            {
                "owner": "demo",
                "as_of": "2026-03-30",
                "var": {"window_days": 365, "confidence": 0.95, "random_metric": 22.5},
                "sharpe_ratio": 1.23,
            }
        )


def test_check_var_structure_rejects_zero_or_negative_var() -> None:
    with pytest.raises(ValueError, match="VaR must be finite and > 0"):
        validate_var_payload({"owner": "demo", "as_of": "2026-03-30", "var": 0.0})

    with pytest.raises(ValueError, match="VaR must be finite and > 0"):
        validate_var_payload({"owner": "demo", "as_of": "2026-03-30", "var": -5.0})


def test_check_var_structure_rejects_non_dict_payload() -> None:
    with pytest.raises(ValueError, match="VaR numeric value not found"):
        validate_var_payload(["not-a-dict"])


def test_check_var_structure_does_not_false_positive_on_string_content() -> None:
    validate_var_payload(
        {
            "owner": "NaNcy",
            "note": "null-safe",
            "as_of": "2026-03-30",
            "var": {"1d": 100.0},
        }
    )


def test_check_var_structure_rejects_boolean_horizon_values() -> None:
    with pytest.raises(ValueError, match="VaR numeric value not found"):
        validate_var_payload(
            {
                "owner": "demo",
                "as_of": "2026-03-30",
                "var": {"window_days": 365, "confidence": 0.95, "1d": True},
                "sharpe_ratio": 1.23,
            }
        )


def test_check_var_structure_rejects_infinite_horizon_value() -> None:
    with pytest.raises(ValueError, match="VaR payload contains NaN/null"):
        validate_var_payload(
            {
                "owner": "demo",
                "as_of": "2026-03-30",
                "var": {"window_days": 365, "confidence": 0.95, "1d": float("inf")},
            }
        )


def test_validate_var_payload_file_accepts_valid_payload(tmp_path) -> None:
    payload_file = tmp_path / "var_payload.json"
    payload_file.write_text(
        '{"owner":"demo","as_of":"2026-03-30","var":{"1d":125.0,"10d":460.0}}',
        encoding="utf-8",
    )
    validate_var_payload_file(payload_file)


def test_strict_runner_delegates_to_shared_var_validator() -> None:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "qa" / "run_issue_2581_strict.sh"
    script_text = script_path.read_text(encoding="utf-8")
    assert 'python3 scripts/qa/var_payload_validator.py "$json_file"' in script_text
