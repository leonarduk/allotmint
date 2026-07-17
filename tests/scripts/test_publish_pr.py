import scripts.dev_tools.publish_pr as publish_pr


class _FakeResult:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def _merge_base_calls(calls):
    return [c for c in calls if c[:2] == ["git", "merge-base"]]


def test_get_changed_files_uses_origin_prefixed_default_branch(monkeypatch):
    """merge-base/diff must run against origin/<default_branch>, not a bare local ref."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["git", "diff", "--name-only", "HEAD"]:
            return _FakeResult(0, "")
        if cmd[:2] == ["git", "merge-base"]:
            return _FakeResult(0, "abc123")
        return _FakeResult(1, "")

    monkeypatch.setattr(publish_pr.subprocess, "run", fake_run)

    publish_pr.get_changed_files("feature-branch", default_branch="master")

    assert _merge_base_calls(calls) == [["git", "merge-base", "feature-branch", "origin/master"]]


def test_get_changed_files_defaults_to_origin_main(monkeypatch):
    """With no default_branch supplied, the merge-base ref falls back to origin/main."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeResult(1, "")

    monkeypatch.setattr(publish_pr.subprocess, "run", fake_run)

    publish_pr.get_changed_files("feature-branch")

    assert _merge_base_calls(calls) == [["git", "merge-base", "feature-branch", "origin/main"]]
