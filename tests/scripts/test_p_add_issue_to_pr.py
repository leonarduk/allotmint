import json

import pytest

import scripts.developer_tools.p_add_issue_to_pr as i


def _pr(number=42, title="Fix flaky login test", body="", files=None):
    return i.PullRequest(number=number, title=title, body=body, files=files or [])


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.mark.parametrize(
    "body",
    [
        "Closes #123",
        "closes #123",
        "This closes: #123",
        "Fixes #99",
        "fix #99",
        "Fixed #99",
        "Resolves #7",
        "resolve #7",
        "Resolved #7",
        "See also #1, but this one Closed #123 for real",
    ],
)
def test_has_linked_issue_true(body):
    assert i.has_linked_issue(body)


@pytest.mark.parametrize(
    "body",
    [
        "",
        "No issue reference here.",
        "See #123 for context.",
        "Related to #123.",
    ],
)
def test_has_linked_issue_false(body):
    assert not i.has_linked_issue(body)


def test_fetch_open_prs_parses_payload(monkeypatch):
    payload = json.dumps(
        [
            {
                "number": 42,
                "title": "Fix flaky login test",
                "body": "No linked issue.",
                "files": [{"path": "tests/test_login.py"}, {"path": ""}],
            }
        ]
    )
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(0, payload))
    prs = i.fetch_open_prs("owner", "repo")
    assert len(prs) == 1
    assert prs[0].number == 42
    assert prs[0].title == "Fix flaky login test"
    assert prs[0].files == ["tests/test_login.py"]


def test_fetch_open_prs_exits_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(1, "", "boom"))
    with pytest.raises(SystemExit) as exc_info:
        i.fetch_open_prs("owner", "repo")
    assert exc_info.value.code == 1


def test_build_issue_body_includes_key_sections():
    pr = _pr(body="Some PR description.", files=["a.py", "b.py"])
    body = i.build_issue_body(pr)
    assert "PR #42" in body
    assert "Some PR description." in body
    assert "a.py\nb.py" in body
    assert "## Value" in body
    assert i.DEFAULT_VALUE_LABEL in body
    assert "- [ ] PR #42 is merged" in body


def test_build_issue_body_falls_back_when_no_files_or_body():
    pr = _pr(body="", files=[])
    body = i.build_issue_body(pr)
    assert "See PR #42" in body


def test_create_issue_parses_issue_number(monkeypatch):
    def fake_run_gh(args):
        if args[:2] == ["label", "list"]:
            return _FakeResult(0, '[{"name": "bug"}]')
        return _FakeResult(0, "https://github.com/o/r/issues/55\n")

    monkeypatch.setattr(i, "run_gh", fake_run_gh)
    assert i.create_issue("o", "r", "Title", "Body", ["bug"]) == 55


def test_create_issue_skips_missing_label_and_continues(monkeypatch, capsys):
    calls = []

    def fake_run_gh(args):
        calls.append(args)
        if args[:2] == ["label", "list"]:
            return _FakeResult(0, '[{"name": "bug"}]')
        return _FakeResult(0, "https://github.com/o/r/issues/55\n")

    monkeypatch.setattr(i, "run_gh", fake_run_gh)

    assert i.create_issue("o", "r", "Title", "Body", ["bug", "missing"]) == 55
    assert calls[1][-2:] == ["--label", "bug"]
    assert "label 'missing' does not exist" in capsys.readouterr().err


def test_create_issue_continues_without_labels_when_lookup_fails(monkeypatch, capsys):
    calls = []

    def fake_run_gh(args):
        calls.append(args)
        if args[:2] == ["label", "list"]:
            return _FakeResult(1, stderr="label lookup failed")
        return _FakeResult(0, "https://github.com/o/r/issues/55\n")

    monkeypatch.setattr(i, "run_gh", fake_run_gh)

    assert i.create_issue("o", "r", "Title", "Body", ["bug"]) == 55
    assert "--label" not in calls[1]
    assert "could not verify configured labels" in capsys.readouterr().err


def test_create_issue_returns_none_on_gh_failure(monkeypatch):
    def fake_run_gh(args):
        if args[:2] == ["label", "list"]:
            return _FakeResult(0, '[{"name": "bug"}]')
        return _FakeResult(1, "", "boom")

    monkeypatch.setattr(i, "run_gh", fake_run_gh)
    assert i.create_issue("o", "r", "Title", "Body", ["bug"]) is None


def test_create_issue_returns_none_when_url_unparseable(monkeypatch):
    def fake_run_gh(args):
        if args[:2] == ["label", "list"]:
            return _FakeResult(0, '[{"name": "bug"}]')
        return _FakeResult(0, "not a url")

    monkeypatch.setattr(i, "run_gh", fake_run_gh)
    assert i.create_issue("o", "r", "Title", "Body", ["bug"]) is None


def test_update_pr_body_appends_closes_line(monkeypatch):
    captured = {}

    def fake_run_gh(args):
        body_file = args[args.index("--body-file") + 1]
        with open(body_file, encoding="utf-8") as f:
            captured["body"] = f.read()
        return _FakeResult(0)

    monkeypatch.setattr(i, "run_gh", fake_run_gh)
    pr = _pr(body="Existing description.")
    assert i.update_pr_body("o", "r", pr, 55) is True
    assert captured["body"] == "Existing description.\n\nCloses #55"


def test_update_pr_body_handles_empty_body(monkeypatch):
    captured = {}

    def fake_run_gh(args):
        body_file = args[args.index("--body-file") + 1]
        with open(body_file, encoding="utf-8") as f:
            captured["body"] = f.read()
        return _FakeResult(0)

    monkeypatch.setattr(i, "run_gh", fake_run_gh)
    pr = _pr(body="")
    assert i.update_pr_body("o", "r", pr, 55) is True
    assert captured["body"] == "Closes #55"


def test_update_pr_body_returns_false_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(1, "", "boom"))
    pr = _pr(body="Existing description.")
    assert i.update_pr_body("o", "r", pr, 55) is False


def test_process_pr_skips_when_already_linked(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "create_issue", lambda *a, **k: calls.append("create") or 1)
    pr = _pr(body="Closes #1")
    assert i.process_pr("o", "r", pr, dry_run=False, labels=["bug"]) is True
    assert calls == []


def test_process_pr_dry_run_does_not_create_or_edit(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "create_issue", lambda *a, **k: calls.append("create") or 1)
    monkeypatch.setattr(i, "update_pr_body", lambda *a, **k: calls.append("edit") or True)
    pr = _pr(body="No issue here.")
    assert i.process_pr("o", "r", pr, dry_run=True, labels=["bug"]) is True
    assert calls == []


def test_process_pr_creates_issue_and_updates_pr(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "create_issue", lambda *a, **k: calls.append("create") or 55)
    monkeypatch.setattr(i, "update_pr_body", lambda *a, **k: calls.append("edit") or True)
    pr = _pr(body="No issue here.")
    assert i.process_pr("o", "r", pr, dry_run=False, labels=["bug"]) is True
    assert calls == ["create", "edit"]


def test_process_pr_fails_when_create_issue_fails(monkeypatch):
    monkeypatch.setattr(i, "create_issue", lambda *a, **k: None)
    edit_calls = []
    monkeypatch.setattr(i, "update_pr_body", lambda *a, **k: edit_calls.append(1) or True)
    pr = _pr(body="No issue here.")
    assert i.process_pr("o", "r", pr, dry_run=False, labels=["bug"]) is False
    assert edit_calls == []


def test_process_pr_fails_when_update_pr_body_fails(monkeypatch):
    monkeypatch.setattr(i, "create_issue", lambda *a, **k: 55)
    monkeypatch.setattr(i, "update_pr_body", lambda *a, **k: False)
    pr = _pr(body="No issue here.")
    assert i.process_pr("o", "r", pr, dry_run=False, labels=["bug"]) is False


def test_resolve_repo_uses_explicit_flag():
    assert i.resolve_repo("someowner/somerepo") == ("someowner", "somerepo")


def test_resolve_repo_rejects_malformed_flag():
    with pytest.raises(SystemExit):
        i.resolve_repo("not-a-valid-repo")


def test_resolve_repo_falls_back_to_git_remote(monkeypatch):
    monkeypatch.setattr(i, "get_repo_info", lambda: ("gitowner", "gitrepo"))
    assert i.resolve_repo(None) == ("gitowner", "gitrepo")
