import json

import pytest

import scripts.developer_tools.n_add_issue_to_pr as i


def _pr(number, title="Fix the thing", body="", author="someone"):
    return i.PullRequest(number=number, title=title, body=body, author=author)


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
        "Fixes #45",
        "fixed #45",
        "Resolves #7",
        "resolved: #7",
        "Some text.\n\nCloses #99\n",
    ],
)
def test_has_linked_issue_true_for_close_keywords(body):
    assert i.has_linked_issue(body)


@pytest.mark.parametrize(
    "body",
    ["", "No issue reference here.", "See #123 for context.", "Related to #5"],
)
def test_has_linked_issue_false_without_close_keyword(body):
    assert not i.has_linked_issue(body)


def test_build_issue_body_includes_pr_number_and_title():
    pr = _pr(42, title="Add widget support", body="Some implementation notes.")
    body = i.build_issue_body(pr)
    assert "Add widget support" in body
    assert "PR #42" in body
    assert "Some implementation notes." in body


def test_build_issue_body_falls_back_when_pr_body_empty():
    pr = _pr(42, title="Add widget support", body="")
    body = i.build_issue_body(pr)
    assert "See PR for implementation details." in body


def test_fetch_open_prs_parses_payload(monkeypatch):
    payload = json.dumps(
        [
            {
                "number": 7,
                "title": "Do a thing",
                "body": "No issue link",
                "author": {"login": "alice"},
            }
        ]
    )
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(0, payload))
    prs = i.fetch_open_prs()
    assert len(prs) == 1
    assert prs[0].number == 7
    assert prs[0].title == "Do a thing"
    assert prs[0].author == "alice"


def test_fetch_open_prs_exits_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(1, "", "boom"))
    with pytest.raises(SystemExit) as exc_info:
        i.fetch_open_prs()
    assert exc_info.value.code == 1


def test_fetch_pr_parses_payload(monkeypatch):
    payload = json.dumps(
        {"number": 9, "title": "Single PR", "body": "body text", "author": {"login": "bob"}}
    )
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(0, payload))
    pr = i.fetch_pr(9)
    assert pr.number == 9
    assert pr.author == "bob"


def test_fetch_pr_exits_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(1, "", "boom"))
    with pytest.raises(SystemExit):
        i.fetch_pr(9)


def test_create_issue_dry_run_does_not_call_gh(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args))
    result = i.create_issue(_pr(1), dry_run=True)
    assert result is None
    assert calls == []


def test_create_issue_parses_issue_number_from_url(monkeypatch):
    monkeypatch.setattr(
        i, "_run_gh_once", lambda args: _FakeResult(0, "https://github.com/o/r/issues/555\n")
    )
    result = i.create_issue(_pr(1), dry_run=False)
    assert result == 555


def test_create_issue_returns_none_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "_run_gh_once", lambda args: _FakeResult(1, "", "boom"))
    assert i.create_issue(_pr(1), dry_run=False) is None


def test_create_issue_returns_none_on_unparseable_url(monkeypatch):
    monkeypatch.setattr(i, "_run_gh_once", lambda args: _FakeResult(0, "not a url"))
    assert i.create_issue(_pr(1), dry_run=False) is None


def test_create_issue_does_not_retry(monkeypatch):
    """Issue creation must not go through the retrying run_gh -- it isn't idempotent."""
    calls = []
    monkeypatch.setattr(i, "run_gh", lambda args: calls.append(args) or _FakeResult(0))
    monkeypatch.setattr(
        i, "_run_gh_once", lambda args: _FakeResult(0, "https://github.com/o/r/issues/1\n")
    )
    i.create_issue(_pr(1), dry_run=False)
    assert calls == []


def test_link_issue_to_pr_dry_run_does_not_call_gh(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args))
    assert i.link_issue_to_pr(_pr(1), 42, dry_run=True) is True
    assert calls == []


def test_link_issue_to_pr_calls_gh_pr_edit(monkeypatch):
    calls = []

    def fake_run(args):
        calls.append(args)
        return _FakeResult(0)

    monkeypatch.setattr(i, "_run_gh_once", fake_run)
    assert i.link_issue_to_pr(_pr(3, body="Existing description"), 42, dry_run=False) is True
    assert calls[0][:3] == ["pr", "edit", "3"]
    assert "--body-file" in calls[0]


def test_link_issue_to_pr_returns_false_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "_run_gh_once", lambda args: _FakeResult(1, "", "boom"))
    assert i.link_issue_to_pr(_pr(1), 42, dry_run=False) is False


def test_process_pr_skips_when_already_linked(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "create_issue", lambda pr, dry_run: calls.append(pr.number) or 1)
    pr = _pr(1, body="Closes #5")
    assert i.process_pr(pr, dry_run=True) is True
    assert calls == []


def test_process_pr_creates_and_links_when_unlinked(monkeypatch):
    monkeypatch.setattr(i, "create_issue", lambda pr, dry_run: 77)
    link_calls = []
    monkeypatch.setattr(
        i,
        "link_issue_to_pr",
        lambda pr, issue_number, dry_run: link_calls.append((pr.number, issue_number)) or True,
    )
    pr = _pr(3, body="")
    assert i.process_pr(pr, dry_run=False) is True
    assert link_calls == [(3, 77)]


def test_process_pr_dry_run_does_not_link(monkeypatch):
    monkeypatch.setattr(i, "create_issue", lambda pr, dry_run: None)
    link_calls = []
    monkeypatch.setattr(
        i, "link_issue_to_pr", lambda pr, issue_number, dry_run: link_calls.append(1) or True
    )
    pr = _pr(3, body="")
    assert i.process_pr(pr, dry_run=True) is True
    assert link_calls == []


def test_process_pr_fails_when_issue_creation_fails(monkeypatch):
    monkeypatch.setattr(i, "create_issue", lambda pr, dry_run: None)
    pr = _pr(3, body="")
    assert i.process_pr(pr, dry_run=False) is False


def test_resolve_repo_uses_explicit_flag():
    assert i.resolve_repo("someorg/somerepo") == ("someorg", "somerepo")


def test_resolve_repo_rejects_malformed_explicit_flag():
    with pytest.raises(SystemExit) as exc_info:
        i.resolve_repo("not-a-valid-repo")
    assert exc_info.value.code == 1


def test_resolve_repo_parses_https_git_remote(monkeypatch):
    monkeypatch.setattr(
        i.subprocess,
        "run",
        lambda *a, **k: _FakeResult(0, "https://github.com/someorg/somerepo.git\n"),
    )
    assert i.resolve_repo(None) == ("someorg", "somerepo")


def test_resolve_repo_parses_ssh_git_remote(monkeypatch):
    monkeypatch.setattr(
        i.subprocess,
        "run",
        lambda *a, **k: _FakeResult(0, "git@github.com:someorg/somerepo.git\n"),
    )
    assert i.resolve_repo(None) == ("someorg", "somerepo")


def test_resolve_repo_falls_back_when_remote_lookup_fails(monkeypatch):
    monkeypatch.setattr(i.subprocess, "run", lambda *a, **k: _FakeResult(1, "", "no remote"))
    assert i.resolve_repo(None) == (i.REPO_OWNER, i.REPO_NAME)


def test_run_gh_returns_failing_result_on_timeout(monkeypatch):
    import subprocess

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["gh"], timeout=60)

    monkeypatch.setattr(i.subprocess, "run", _raise_timeout)
    monkeypatch.setattr(i.time, "sleep", lambda seconds: None)
    result = i.run_gh(["pr", "list"])
    assert result.returncode != 0
    assert "timed out" in result.stderr
