"""The one-off/hand-edit migration for #11086 flags covered estimates and touches nothing else."""

from __future__ import annotations

import json

from scripts import mark_dividend_attribution as script

ROWS = [
    {"date": "2026-08-10", "type": "DIVIDEND", "amount_minor": 160815, "comments": "Transfer from Income Account"},
    {
        "date": "2026-07-16",
        "type": "DIVIDEND",
        "ticker": "SEGA.L",
        "amount_minor": 49497,
        "reason": "Automated dividend import",
    },
]


def _write(tmp_path, *, newline: bool):
    path = tmp_path / "steve" / "SIPP_transactions.json"
    path.parent.mkdir()
    text = json.dumps({"owner": "steve", "transactions": ROWS}, indent=2, ensure_ascii=False)
    path.write_text(text + ("\n" if newline else ""), encoding="utf-8")
    return path


def test_dry_run_reports_without_writing(tmp_path, capsys):
    path = _write(tmp_path, newline=True)
    before = path.read_bytes()

    assert script.main([str(tmp_path), "--dry-run"]) == 0

    assert path.read_bytes() == before
    assert "1 row(s) would change in total" in capsys.readouterr().out


def test_flags_covered_estimates_and_keeps_the_file_layout(tmp_path):
    path = _write(tmp_path, newline=False)

    assert script.main([str(tmp_path)]) == 0

    raw = path.read_text(encoding="utf-8")
    assert not raw.endswith("\n")
    rows = json.loads(raw)["transactions"]
    assert rows[1]["attribution_only"] is True
    assert "attribution_only" not in rows[0]
    expected = json.dumps({"owner": "steve", "transactions": rows}, indent=2, ensure_ascii=False)
    assert raw == expected


def test_missing_root_is_an_error(tmp_path):
    assert script.main([str(tmp_path / "nope")]) == 2
