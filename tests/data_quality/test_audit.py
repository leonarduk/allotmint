"""Unit tests for backend/data_quality/audit.py (append-only JSONL, atomic)."""

from __future__ import annotations

import json

import pytest

from backend.data_quality import audit as audit_module
from backend.data_quality.audit import append_audit, find_audit_entry, read_audit


@pytest.fixture
def audit_dir(tmp_path, monkeypatch):
    target = tmp_path / "audit"
    monkeypatch.setattr(audit_module.config, "audit_dir", target)
    return target


def test_append_and_read_roundtrip(audit_dir):
    entry = append_audit(
        action="wrong_exchange",
        issue_id="WRONG_EXCHANGE:demo:isa:MICC.L",
        entity={"owner": "demo", "account": "isa"},
        before={"ticker": "MICC.L"},
        after={"ticker": "MICC.N"},
        actor="user@example.com",
    )
    assert entry["id"]
    assert entry["action"] == "wrong_exchange"

    entries = read_audit()
    assert len(entries) == 1
    assert entries[0]["id"] == entry["id"]
    assert entries[0]["before"] == {"ticker": "MICC.L"}
    assert entries[0]["actor"] == "user@example.com"


def test_append_is_jsonl_and_atomic(audit_dir):
    append_audit(
        action="refetch",
        issue_id="GAPS:ABC:L",
        entity={"ticker": "ABC", "exchange": "L"},
        before={},
        after={"rows": 10},
    )
    lines = (audit_dir / "data_quality_audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    json.loads(lines[0])  # each line is valid JSON
    assert not (audit_dir / "data_quality_audit.jsonl.tmp").exists()


def test_append_preserves_earlier_entries(audit_dir):
    append_audit(action="refetch", issue_id="a", entity={}, before={}, after={})
    append_audit(action="dedupe", issue_id="b", entity={}, before={}, after={})
    entries = read_audit()
    assert len(entries) == 2
    # Newest first.
    assert entries[0]["issue_id"] == "b"


def test_find_audit_entry(audit_dir):
    entry = append_audit(
        action="dedupe", issue_id="DUPLICATES:ABC:L", entity={}, before={}, after={}
    )
    assert find_audit_entry(entry["id"]) is not None
    assert find_audit_entry("missing-id") is None


def test_read_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_module.config, "audit_dir", tmp_path / "no-audit")
    assert read_audit() == []


def test_corrupt_line_is_skipped(audit_dir):
    path = audit_dir / "data_quality_audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json}\n", encoding="utf-8")
    append_audit(action="refetch", issue_id="c", entity={}, before={}, after={})
    entries = read_audit()
    assert len(entries) == 1
    assert entries[0]["issue_id"] == "c"


def test_append_separates_from_content_without_trailing_newline(audit_dir):
    """A file missing its final newline must not merge the next entry."""
    path = audit_dir / "data_quality_audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Simulate a partial write / external edit: no trailing newline.
    path.write_text('{"id":"partial"}', encoding="utf-8")

    append_audit(action="refetch", issue_id="after-partial", entity={}, before={}, after={})

    entries = read_audit()
    assert len(entries) == 2
    ids = {e["issue_id"] for e in entries if "issue_id" in e}
    assert "after-partial" in ids


def test_concurrent_appends_lose_no_entries(audit_dir):
    """O_APPEND single-write semantics must not drop entries under concurrency."""
    import threading

    def writer(index: int) -> None:
        for _ in range(5):
            append_audit(
                action="refetch",
                issue_id=f"w{index}",
                entity={},
                before={},
                after={},
            )

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    entries = read_audit()
    # 8 writers x 5 appends each, no entry lost to a read-append race.
    assert len(entries) == 40
