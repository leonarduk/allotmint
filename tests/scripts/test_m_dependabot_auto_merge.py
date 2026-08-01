import json

import pytest

import scripts.developer_tools.m_dependabot_auto_merge as i


def _pr(number, title="Bump foo", head_ref_name="dependabot/pip/foo-1.2.3", head_sha="",
        mergeable="MERGEABLE", mergeable_state="clean", checks=None):
    return i.PullRequest(
        number=number,
        title=title,
        head_ref_name=head_ref_name,
        head_sha=head_sha,
        mergeable=mergeable,
        mergeable_state=mergeable_state,
        checks=checks if checks is not None else [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
    )


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_checks_have_passed_true_when_all_success():
    checks = [
        {"status": "COMPLETED", "conclusion": "SUCCESS"},
        {"status": "COMPLETED", "conclusion": "NEUTRAL"},
    ]
    assert i.checks_have_passed(checks)


def test_checks_have_passed_false_when_empty():
    assert not i.checks_have_passed([])


def test_checks_have_passed_false_when_one_failing():
    checks = [
        {"status": "COMPLETED", "conclusion": "SUCCESS"},
        {"status": "COMPLETED", "conclusion": "FAILURE"},
    ]
    assert not i.checks_have_passed(checks)


def test_checks_have_passed_false_when_pending():
    checks = [{"status": "IN_PROGRESS", "conclusion": ""}]
    assert not i.checks_have_passed(checks)


def test_is_mergeable_true_when_clean():
    assert i.is_mergeable(_pr(1, mergeable="MERGEABLE", mergeable_state="clean"))


def test_is_mergeable_true_when_only_behind_main():
    assert i.is_mergeable(_pr(1, mergeable="MERGEABLE", mergeable_state="behind"))


def test_is_mergeable_false_when_dirty():
    assert not i.is_mergeable(_pr(1, mergeable="MERGEABLE", mergeable_state="dirty"))


def test_is_mergeable_false_when_conflicting_even_if_state_looks_clean():
    """Real conflicts must be rejected regardless of a stale/odd mergeable_state."""
    assert not i.is_mergeable(_pr(1, mergeable="CONFLICTING", mergeable_state="clean"))


def test_is_mergeable_false_when_mergeable_is_none_and_state_empty():
    assert not i.is_mergeable(_pr(1, mergeable=None, mergeable_state=""))


def test_is_mergeable_false_when_state_unknown():
    assert not i.is_mergeable(_pr(1, mergeable="MERGEABLE", mergeable_state="unknown"))


def test_fetch_open_dependabot_prs_parses_payload(monkeypatch):
    payload = json.dumps(
        [
            {
                "number": 42,
                "title": "Bump requests from 2.0 to 2.1",
                "headRefName": "dependabot/pip/requests-2.1",
                "headRefOid": "abc123",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
            }
        ]
    )
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(0, payload))
    prs = i.fetch_open_dependabot_prs()
    assert len(prs) == 1
    assert prs[0].number == 42
    assert prs[0].head_ref_name == "dependabot/pip/requests-2.1"
    assert prs[0].head_sha == "abc123"
    assert prs[0].mergeable == "MERGEABLE"
    assert prs[0].mergeable_state == "clean"


def test_fetch_open_dependabot_prs_exits_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(1, "", "boom"))
    with pytest.raises(SystemExit) as exc_info:
        i.fetch_open_dependabot_prs()
    assert exc_info.value.code == 1


def test_fetch_mergeability_parses_payload(monkeypatch):
    payload = json.dumps({"mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"})
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(0, payload))
    mergeable, state = i.fetch_mergeability(42)
    assert mergeable == "MERGEABLE"
    assert state == "behind"


def test_fetch_mergeability_returns_unknown_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(1, "", "boom"))
    mergeable, state = i.fetch_mergeability(42)
    assert mergeable is None
    assert state == ""


def test_resolve_mergeability_skips_refetch_when_already_known(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "fetch_mergeability", lambda number: calls.append(number) or ("MERGEABLE", "clean"))
    pr = _pr(1, mergeable="MERGEABLE", mergeable_state="clean")
    i.resolve_mergeability(pr)
    assert calls == []


def test_resolve_mergeability_refetches_when_unknown(monkeypatch):
    monkeypatch.setattr(i, "fetch_mergeability", lambda number: ("MERGEABLE", "behind"))
    pr = _pr(1, mergeable="UNKNOWN", mergeable_state="unknown")
    i.resolve_mergeability(pr)
    assert pr.mergeable == "MERGEABLE"
    assert pr.mergeable_state == "behind"


def test_resolve_mergeability_retries_then_gives_up(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "fetch_mergeability", lambda number: calls.append(number) or ("UNKNOWN", "unknown"))
    monkeypatch.setattr(i.time, "sleep", lambda seconds: None)
    pr = _pr(1, mergeable="UNKNOWN", mergeable_state="unknown")
    i.resolve_mergeability(pr)
    assert len(calls) == i.MERGEABILITY_REFRESH_ATTEMPTS
    assert pr.mergeable_state == "unknown"


def test_process_pr_refreshes_mergeability_before_checking(monkeypatch):
    monkeypatch.setattr(i, "resolve_mergeability", lambda pr: setattr(pr, "mergeable_state", "clean"))
    calls = []
    monkeypatch.setattr(i, "merge_and_delete", lambda pr, dry_run, admin=False: calls.append(pr.number) or True)
    pr = _pr(1, mergeable_state="unknown")
    assert i.process_pr(pr, dry_run=True) is True
    assert calls == [1]


def test_process_pr_skips_when_checks_not_passed(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "merge_and_delete", lambda pr, dry_run, admin=False: calls.append(pr.number) or True)
    pr = _pr(1, checks=[{"status": "COMPLETED", "conclusion": "FAILURE"}])
    assert i.process_pr(pr, dry_run=True) is True
    assert calls == []


def test_process_pr_skips_when_not_mergeable(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "merge_and_delete", lambda pr, dry_run, admin=False: calls.append(pr.number) or True)
    pr = _pr(1, mergeable_state="dirty")
    assert i.process_pr(pr, dry_run=True) is True
    assert calls == []


def test_process_pr_force_merges_when_green_and_only_behind_default_strategy(monkeypatch):
    merge_calls = []
    monkeypatch.setattr(
        i, "merge_and_delete", lambda pr, dry_run, admin=False: merge_calls.append((pr.number, admin)) or True
    )
    pr = _pr(1, mergeable_state="behind")
    assert i.process_pr(pr, dry_run=True) is True
    assert merge_calls == [(1, True)]


def test_process_pr_merges_directly_when_clean(monkeypatch):
    merge_calls = []
    monkeypatch.setattr(
        i, "merge_and_delete", lambda pr, dry_run, admin=False: merge_calls.append((pr.number, admin)) or True
    )
    pr = _pr(1, mergeable_state="clean")
    assert i.process_pr(pr, dry_run=True) is True
    assert merge_calls == [(1, False)]


def test_process_pr_behind_strategy_update_branch(monkeypatch):
    merge_calls = []
    update_calls = []
    monkeypatch.setattr(i, "merge_and_delete", lambda pr, dry_run, admin=False: merge_calls.append(pr.number) or True)
    monkeypatch.setattr(i, "update_branch", lambda pr, dry_run: update_calls.append(pr.number) or True)
    pr = _pr(1, mergeable_state="behind")
    assert i.process_pr(pr, dry_run=True, behind_strategy="update-branch") is True
    assert update_calls == [1]
    assert merge_calls == []


def test_process_pr_behind_strategy_skip(monkeypatch):
    merge_calls = []
    update_calls = []
    monkeypatch.setattr(i, "merge_and_delete", lambda pr, dry_run, admin=False: merge_calls.append(pr.number) or True)
    monkeypatch.setattr(i, "update_branch", lambda pr, dry_run: update_calls.append(pr.number) or True)
    pr = _pr(1, mergeable_state="behind")
    assert i.process_pr(pr, dry_run=True, behind_strategy="skip") is True
    assert merge_calls == []
    assert update_calls == []


def test_process_pr_propagates_merge_failure(monkeypatch):
    monkeypatch.setattr(i, "merge_and_delete", lambda pr, dry_run, admin=False: False)
    pr = _pr(1, mergeable_state="clean")
    assert i.process_pr(pr, dry_run=False) is False


def test_process_pr_propagates_update_branch_failure(monkeypatch):
    monkeypatch.setattr(i, "update_branch", lambda pr, dry_run: False)
    pr = _pr(1, mergeable_state="behind")
    assert i.process_pr(pr, dry_run=False, behind_strategy="update-branch") is False


def test_update_branch_dry_run_does_not_call_gh(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args))
    assert i.update_branch(_pr(1), dry_run=True) is True
    assert calls == []


def test_update_branch_calls_gh_pr_update_branch(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args) or _FakeResult(0))
    assert i.update_branch(_pr(7), dry_run=False) is True
    assert calls == [["pr", "update-branch", "7"]]


def test_update_branch_returns_false_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "_run_gh_once", lambda args: _FakeResult(1, "", "boom"))
    assert i.update_branch(_pr(1), dry_run=False) is False


def test_update_branch_does_not_retry(monkeypatch):
    """Branch update must not go through the retrying run_gh -- it isn't idempotent."""
    calls = []
    monkeypatch.setattr(i, "run_gh", lambda args: calls.append(args) or _FakeResult(0))
    monkeypatch.setattr(i, "_run_gh_once", lambda args: _FakeResult(0))
    i.update_branch(_pr(1), dry_run=False)
    assert calls == []


def test_merge_and_delete_dry_run_does_not_call_gh(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args))
    assert i.merge_and_delete(_pr(1), dry_run=True) is True
    assert calls == []


def test_merge_and_delete_calls_gh_pr_merge(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args) or _FakeResult(0))
    result = i.merge_and_delete(
        _pr(1, head_ref_name="dependabot/pip/foo-1.2.3", head_sha="deadbeef"), dry_run=False
    )
    assert result is True
    assert calls == [["pr", "merge", "1", "--squash", "--delete-branch", "--match-head-commit", "deadbeef"]]


def test_merge_and_delete_omits_match_head_commit_when_sha_unknown(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args) or _FakeResult(0))
    assert i.merge_and_delete(_pr(1, head_sha=""), dry_run=False) is True
    assert calls == [["pr", "merge", "1", "--squash", "--delete-branch"]]


def test_merge_and_delete_returns_false_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "_run_gh_once", lambda args: _FakeResult(1, "", "boom"))
    assert i.merge_and_delete(_pr(1), dry_run=False) is False


def test_merge_and_delete_adds_admin_flag_when_requested(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args) or _FakeResult(0))
    assert i.merge_and_delete(_pr(1, head_sha="deadbeef"), dry_run=False, admin=True) is True
    assert calls == [
        ["pr", "merge", "1", "--squash", "--delete-branch", "--match-head-commit", "deadbeef", "--admin"]
    ]


def test_merge_and_delete_omits_admin_flag_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args) or _FakeResult(0))
    i.merge_and_delete(_pr(1, head_sha=""), dry_run=False)
    assert "--admin" not in calls[0]


def test_merge_and_delete_does_not_retry(monkeypatch):
    """Merge must not go through the retrying run_gh -- it isn't idempotent."""
    calls = []
    monkeypatch.setattr(i, "run_gh", lambda args: calls.append(args) or _FakeResult(0))
    monkeypatch.setattr(i, "_run_gh_once", lambda args: _FakeResult(0))
    assert i.merge_and_delete(_pr(1), dry_run=False) is True
    assert calls == []


def test_merge_and_delete_refuses_protected_branch(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "_run_gh_once", lambda args: calls.append(args) or _FakeResult(0))
    assert i.merge_and_delete(_pr(1, head_ref_name="main"), dry_run=False) is False
    assert calls == []


def test_resolve_repo_uses_explicit_flag(monkeypatch):
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
