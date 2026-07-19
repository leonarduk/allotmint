"""Unit tests for sync_issues script."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "developer_tools"))
import a_sync_issues  # noqa: E402


def _issue(number: int, title: str = "Some issue", state: str = "open") -> dict:
    return {
        "number": number,
        "title": title,
        "html_url": f"https://github.com/leonarduk/allotmint/issues/{number}",
        "labels": [],
        "state": state,
        "body": "body text",
    }


def _run_main(monkeypatch, tmp_path, open_issues, closed_issues):
    monkeypatch.setattr(a_sync_issues, "ISSUES_DIR", tmp_path)
    monkeypatch.setattr(a_sync_issues, "get_github_token", lambda: "fake-token")

    def fake_fetch_issues(token, state):
        return open_issues if state == "open" else closed_issues

    monkeypatch.setattr(a_sync_issues, "fetch_issues", fake_fetch_issues)
    a_sync_issues.main()


def test_reopened_issue_file_is_not_deleted(monkeypatch, tmp_path):
    """An issue appearing in both the open and closed fetches (e.g. a race between the two
    paginated calls, or a reopen mid-sync) must keep its file rather than being deleted."""
    issue = _issue(4521, title="Reopened issue")
    _run_main(monkeypatch, tmp_path, open_issues=[issue], closed_issues=[issue])

    filepath = tmp_path / a_sync_issues.make_filename(4521, "Reopened issue")
    assert filepath.exists()


def test_genuinely_closed_issue_file_is_deleted(monkeypatch, tmp_path):
    filename = a_sync_issues.make_filename(4522, "Closed issue")
    (tmp_path / filename).write_text("stale content", encoding="utf-8")

    _run_main(
        monkeypatch,
        tmp_path,
        open_issues=[],
        closed_issues=[_issue(4522, title="Closed issue", state="closed")],
    )

    assert not (tmp_path / filename).exists()


def test_open_issue_file_is_created(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, open_issues=[_issue(4523, title="Open issue")], closed_issues=[])

    filepath = tmp_path / a_sync_issues.make_filename(4523, "Open issue")
    assert filepath.exists()
    assert "Open issue" in filepath.read_text(encoding="utf-8")
