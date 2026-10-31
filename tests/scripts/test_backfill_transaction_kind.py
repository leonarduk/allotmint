"""The #10797 backfill sets ``kind`` on unambiguous rows only, never overwrites one, and is idempotent."""

from __future__ import annotations

import json

from scripts import backfill_transaction_kind as script

SIPP_ROWS = [
    {"date": "2026-05-01", "type": "DEPOSIT", "amount_minor": 80_000, "comments": "Personal contribution"},
    {"date": "2026-06-10", "type": "DEPOSIT", "amount_minor": 20_000, "comments": "Tax relief"},
    {"date": "2026-06-11", "type": "DEPOSIT", "amount_minor": 9_000_000, "comments": "Transfer of contribution"},
    {"date": "2026-06-12", "type": "DEPOSIT", "amount_minor": 5_000, "kind": None},
    {"date": "2026-06-13", "type": "DEPOSIT", "amount_minor": 5_000, "comments": "Tax relief", "kind": "manual"},
    {"date": "2026-06-14", "type": "BUY", "ticker": "VWRL.L", "units": 1, "price_gbp": 100.0},
]


def _write(tmp_path, rows, *, account="sipp", newline=True):
    path = tmp_path / "alex" / f"{account}_transactions.json"
    path.parent.mkdir(exist_ok=True)
    text = json.dumps({"owner": "alex", "account_type": account, "transactions": rows}, indent=2)
    path.write_text(text + ("\n" if newline else ""), encoding="utf-8")
    return path


def test_dry_run_reports_without_writing(tmp_path, capsys):
    path = _write(tmp_path, SIPP_ROWS)
    before = path.read_bytes()

    assert script.main([str(tmp_path), "--dry-run"]) == 0

    assert path.read_bytes() == before
    out = capsys.readouterr().out
    assert "2 row(s) would be classified in total; 2 cash row(s) left unclassified" in out
    assert "Transfer of contribution" in out


def test_classifies_unambiguous_rows_and_keeps_the_layout(tmp_path):
    path = _write(tmp_path, SIPP_ROWS, newline=False)

    assert script.main([str(tmp_path)]) == 0

    raw = path.read_text(encoding="utf-8")
    assert not raw.endswith("\n")
    data = json.loads(raw)
    assert [row.get("kind") for row in data["transactions"]] == [
        "personal_contribution",
        "tax_relief",
        None,
        None,
        "manual",
        None,
    ]
    assert "kind" not in data["transactions"][2]
    assert "kind" not in data["transactions"][5]
    assert raw == json.dumps(data, indent=2)


def test_second_run_changes_nothing(tmp_path, capsys):
    path = _write(tmp_path, SIPP_ROWS)
    script.main([str(tmp_path)])
    after_first = path.read_bytes()
    capsys.readouterr()

    assert script.main([str(tmp_path)]) == 0

    assert path.read_bytes() == after_first
    assert "0 row(s) classified in total" in capsys.readouterr().out


def test_account_falls_back_to_the_file_name(tmp_path):
    path = tmp_path / "alex" / "isa_transactions.json"
    path.parent.mkdir()
    rows = [{"date": "2026-05-01", "type": "DEPOSIT", "amount_minor": 1_000}]
    path.write_text(json.dumps({"owner": "alex", "transactions": rows}, indent=2) + "\n", encoding="utf-8")

    script.main([str(tmp_path)])

    assert json.loads(path.read_text(encoding="utf-8"))["transactions"][0]["kind"] == "isa_subscription"


def test_file_with_nothing_to_classify_is_not_touched(tmp_path):
    rows = [{"date": "2026-05-01", "type": "DEPOSIT", "amount_minor": 1_000, "comments": "Payment"}]
    path = _write(tmp_path, rows)
    path.write_text(path.read_text(encoding="utf-8").replace("  ", "    "), encoding="utf-8")
    before = path.read_bytes()

    script.main([str(tmp_path)])

    assert path.read_bytes() == before


def test_legacy_account_kind_is_kept_and_counted(tmp_path, capsys):
    rows = [
        # Would classify as personal_contribution / withdrawal if kind were null.
        {"date": "2026-05-01", "type": "DEPOSIT", "amount_minor": 1_000, "comments": "Personal contribution",
         "kind": "account"},
        {"date": "2026-05-02", "type": "WITHDRAWAL", "amount_minor": -500, "kind": "account"},
        {"date": "2026-05-03", "type": "income", "amount_minor": 200, "kind": "account"},
        {"date": "2026-05-04", "type": "DEPOSIT", "amount_minor": 1_000, "comments": "Tax relief"},
    ]  # fmt: skip
    path = _write(tmp_path, rows)

    for _ in range(2):
        assert script.main([str(tmp_path)]) == 0
        data = json.loads(path.read_text(encoding="utf-8"))
        assert [row.get("kind") for row in data["transactions"]] == ["account", "account", "account", "tax_relief"]

    out = capsys.readouterr().out
    assert out.count('alex/sipp_transactions.json: 3 row(s) with legacy kind "account" left as is') == 2
    assert out.count('3 row(s) with legacy kind "account" left as is (not a cash classification)') == 2


def test_missing_root_is_an_error(tmp_path):
    assert script.main([str(tmp_path / "nope")]) == 2
