from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path("scripts/qa/run_issue_2581_strict.sh")


def _load_var_parser_snippet() -> str:
    script_text = SCRIPT_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r"check_var_structure\(\)\s*\{.*?<<'PY'\n(.*?)\nPY\n\}", re.DOTALL)
    match = pattern.search(script_text)
    if not match:
        raise AssertionError("Could not locate check_var_structure parser snippet")
    return match.group(1)


def _run_var_parser(payload: dict, payload_file: Path) -> subprocess.CompletedProcess[str]:
    snippet = _load_var_parser_snippet()
    payload_file.parent.mkdir(parents=True, exist_ok=True)
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", snippet, str(payload_file)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_var_structure_accepts_nested_var_payload(tmp_path: Path) -> None:
    result = _run_var_parser(
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
        },
        tmp_path / "var_payload.json",
    )

    assert result.returncode == 0, result.stderr


def test_check_var_structure_rejects_payload_without_numeric_var(tmp_path: Path) -> None:
    result = _run_var_parser(
        {
            "owner": "demo",
            "as_of": "2026-03-30",
            "var": {"window_days": 365, "confidence": 0.95},
            "sharpe_ratio": 1.23,
        },
        tmp_path / "var_payload.json",
    )

    assert result.returncode != 0
    assert "VaR numeric value not found" in result.stderr


def test_check_var_structure_accepts_alternative_horizon_key(tmp_path: Path) -> None:
    result = _run_var_parser(
        {
            "owner": "demo",
            "as_of": "2026-03-30",
            "var": {"window_days": 365, "confidence": 0.95, "30d": 987.65},
            "sharpe_ratio": 1.23,
        },
        tmp_path / "var_payload.json",
    )

    assert result.returncode == 0, result.stderr


def test_check_var_structure_rejects_non_horizon_numeric_nested_key(tmp_path: Path) -> None:
    result = _run_var_parser(
        {
            "owner": "demo",
            "as_of": "2026-03-30",
            "var": {"window_days": 365, "confidence": 0.95, "random_metric": 22.5},
            "sharpe_ratio": 1.23,
        },
        tmp_path / "var_payload.json",
    )

    assert result.returncode != 0
    assert "VaR numeric value not found" in result.stderr
