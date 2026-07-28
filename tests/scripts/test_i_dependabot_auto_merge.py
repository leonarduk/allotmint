import json

import scripts.developer_tools.i_dependabot_auto_merge as i


def _pr(number, title="Bump foo", head_ref_name="dependabot/pip/foo-1.2.3",
        mergeable=True, mergeable_state="clean", checks=None):
    return i.PullRequest(
        number=number,
        title=title,
        head_ref_name=head_ref_name,
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
    assert i.is_mergeable(_pr(1, mergeable=True, mergeable_state="clean"))


def test_is_mergeable_true_when_only_behind_main():
    assert i.is_mergeable(_pr(1, mergeable=True, mergeable_state="behind"))


def test_is_mergeable_false_when_dirty():
    assert not i.is_mergeable(_pr(1, mergeable=True, mergeable_state="dirty"))


def test_is_mergeable_false_when_mergeable_flag_false():
    assert not i.is_mergeable(_pr(1, mergeable=False, mergeable_state="clean"))


def test_fetch_open_dependabot_prs_parses_payload(monkeypatch):
    payload = json.dumps(
        [
            {
                "number": 42,
                "title": "Bump requests from 2.0 to 2.1",
                "headRefName": "dependabot/pip/requests-2.1",
                "headRefOid": "abc123",
                "mergeable": True,
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
    assert prs[0].mergeable_state == "clean"


def test_fetch_open_dependabot_prs_exits_on_gh_failure(monkeypatch):
    monkeypatch.setattr(i, "run_gh", lambda args: _FakeResult(1, "", "boom"))
    try:
        i.fetch_open_dependabot_prs()
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 1


def test_process_pr_skips_when_checks_not_passed(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "merge_and_delete", lambda pr, dry_run: calls.append(pr.number))
    pr = _pr(1, checks=[{"status": "COMPLETED", "conclusion": "FAILURE"}])
    i.process_pr(pr, dry_run=True)
    assert calls == []


def test_process_pr_skips_when_not_mergeable(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "merge_and_delete", lambda pr, dry_run: calls.append(pr.number))
    pr = _pr(1, mergeable_state="dirty")
    i.process_pr(pr, dry_run=True)
    assert calls == []


def test_process_pr_merges_when_green_and_only_behind(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "merge_and_delete", lambda pr, dry_run: calls.append(pr.number))
    pr = _pr(1, mergeable_state="behind")
    i.process_pr(pr, dry_run=True)
    assert calls == [1]


def test_merge_and_delete_dry_run_does_not_call_gh(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "run_gh", lambda args: calls.append(args))
    i.merge_and_delete(_pr(1), dry_run=True)
    assert calls == []


def test_merge_and_delete_calls_gh_pr_merge(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "run_gh", lambda args: calls.append(args) or _FakeResult(0))
    i.merge_and_delete(_pr(1, head_ref_name="dependabot/pip/foo-1.2.3"), dry_run=False)
    assert calls == [["pr", "merge", "1", "--squash", "--delete-branch"]]


def test_merge_and_delete_refuses_protected_branch(monkeypatch):
    calls = []
    monkeypatch.setattr(i, "run_gh", lambda args: calls.append(args) or _FakeResult(0))
    i.merge_and_delete(_pr(1, head_ref_name="main"), dry_run=False)
    assert calls == []
