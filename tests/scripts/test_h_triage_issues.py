import json

import scripts.developer_tools.h_triage_issues as h


def _issue(number, title, body="", labels=None):
    return h.Issue(number=number, title=title, body=body, labels=labels or [])


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_is_scoped_apart_matches_tracked_separately():
    body = "This is out of scope, tracked separately as #123 for follow-up."
    assert h.is_scoped_apart(body, 123)
    assert not h.is_scoped_apart(body, 456)


def test_is_scoped_apart_matches_out_of_scope():
    body = "Out of scope: #789"
    assert h.is_scoped_apart(body, 789)


def test_referenced_issue_numbers_extracts_all_refs():
    body = "Follows up on #10 and also relates to #20, not #10 twice though."
    assert h.referenced_issue_numbers(body) == {10, 20}


def test_find_candidate_groups_unions_cross_referencing_issues():
    issues = [
        _issue(1, "First nit", body="Follow-up from #2"),
        _issue(2, "Second nit", body="See also #1"),
        _issue(3, "Unrelated standalone", body="No references here"),
    ]
    groups = h.find_candidate_groups(issues)
    assert len(groups) == 1
    assert {i.number for i in groups[0]} == {1, 2}


def test_find_candidate_groups_respects_scope_apart_guard():
    issues = [
        _issue(1, "First", body="Related to #2, but tracked separately as #2"),
        _issue(2, "Second", body="Related to #1"),
    ]
    groups = h.find_candidate_groups(issues)
    assert groups == []


def test_find_candidate_groups_ignores_refs_outside_the_unmilestoned_set():
    issues = [
        _issue(1, "First", body="Introduced by #999"),
    ]
    groups = h.find_candidate_groups(issues)
    assert groups == []


def test_parse_classifications_reads_number_and_label():
    response = "#5: DUPLICATE\n#6: fold\nsome preamble\n#7: STANDALONE"
    result = h.parse_classifications(response)
    assert result == {5: "DUPLICATE", 6: "FOLD", 7: "STANDALONE"}


def test_classify_single_issue_detects_new_feature(monkeypatch):
    monkeypatch.setattr(h, "fetch_ollama_review", lambda endpoint, model, prompt: "NEW_FEATURE")
    issue = _issue(1, "Add dark mode toggle")
    assert h.classify_single_issue(issue, "model", "endpoint") == "NEW_FEATURE"


def test_classify_single_issue_defaults_to_backlog(monkeypatch):
    monkeypatch.setattr(h, "fetch_ollama_review", lambda endpoint, model, prompt: "BACKLOG")
    issue = _issue(1, "Add missing test coverage")
    assert h.classify_single_issue(issue, "model", "endpoint") == "BACKLOG"


def test_fetch_unmilestoned_open_issues_filters_milestoned(monkeypatch):
    payload = json.dumps(
        [
            {"number": 1, "title": "No milestone", "labels": [], "milestone": None},
            {
                "number": 2,
                "title": "Has milestone",
                "labels": [{"name": "bug"}],
                "milestone": {"title": "Backend Hardening & Test Coverage"},
            },
        ]
    )
    monkeypatch.setattr(h, "run_gh", lambda args: _FakeResult(0, payload))
    issues = h.fetch_unmilestoned_open_issues()
    assert [i.number for i in issues] == [1]


def test_fetch_unmilestoned_open_issues_exits_on_gh_failure(monkeypatch):
    monkeypatch.setattr(h, "run_gh", lambda args: _FakeResult(1, "", "boom"))
    try:
        h.fetch_unmilestoned_open_issues()
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 1


def test_fetch_issue_body_returns_empty_on_failure(monkeypatch):
    monkeypatch.setattr(h, "run_gh", lambda args: _FakeResult(1, "", "not found"))
    assert h.fetch_issue_body(999) == ""


def test_fetch_issue_body_returns_body_text(monkeypatch):
    monkeypatch.setattr(h, "run_gh", lambda args: _FakeResult(0, json.dumps({"body": "hello"})))
    assert h.fetch_issue_body(1) == "hello"


def test_close_issue_dry_run_does_not_call_gh(monkeypatch):
    calls = []
    monkeypatch.setattr(h, "run_gh", lambda args: calls.append(args))
    h.close_issue(1, "dup", dry_run=True)
    assert calls == []


def test_close_issue_calls_gh_with_not_planned_reason(monkeypatch):
    calls = []
    monkeypatch.setattr(h, "run_gh", lambda args: calls.append(args))
    h.close_issue(1, "dup reason", dry_run=False)
    assert calls == [["issue", "close", "1", "--reason", "not planned", "--comment", "dup reason"]]


def test_assign_milestone_calls_gh_edit(monkeypatch):
    calls = []
    monkeypatch.setattr(h, "run_gh", lambda args: calls.append(args))
    h.assign_milestone(5, h.CONSOLIDATOR_MILESTONE, dry_run=False)
    assert calls == [["issue", "edit", "5", "--milestone", h.CONSOLIDATOR_MILESTONE]]


def test_comment_new_feature_never_touches_milestone(monkeypatch):
    calls = []
    monkeypatch.setattr(h, "run_gh", lambda args: calls.append(args))
    h.comment_new_feature(5, dry_run=False)
    assert len(calls) == 1
    assert calls[0][:2] == ["issue", "comment"]
    assert "--milestone" not in calls[0]


def test_create_consolidator_issue_dry_run_returns_none_and_skips_gh(monkeypatch):
    calls = []
    monkeypatch.setattr(h, "run_gh", lambda args: calls.append(args))
    result = h.create_consolidator_issue("Title", [_issue(1, "A"), _issue(2, "B")], dry_run=True)
    assert result is None
    assert calls == []


def test_create_consolidator_issue_parses_issue_number(monkeypatch):
    monkeypatch.setattr(
        h,
        "run_gh",
        lambda args: _FakeResult(0, "https://github.com/leonarduk/allotmint/issues/4242\n"),
    )
    result = h.create_consolidator_issue("Title", [_issue(1, "A"), _issue(2, "B")], dry_run=False)
    assert result == 4242


def test_create_consolidator_issue_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(h, "run_gh", lambda args: _FakeResult(1, "", "boom"))
    result = h.create_consolidator_issue("Title", [_issue(1, "A")], dry_run=False)
    assert result is None


def test_triage_group_closes_duplicate_keeping_lowest_number(monkeypatch):
    monkeypatch.setattr(h, "fetch_ollama_review", lambda endpoint, model, prompt: "#2: DUPLICATE")
    closed = []
    monkeypatch.setattr(h, "close_issue", lambda number, comment, dry_run: closed.append(number))
    group = [_issue(1, "First"), _issue(2, "Second")]
    handled = h.triage_group(group, "model", "endpoint", dry_run=True)
    assert closed == [2]
    assert handled == {2}


def test_triage_group_does_not_close_canonical_even_if_flagged_duplicate(monkeypatch):
    monkeypatch.setattr(h, "fetch_ollama_review", lambda endpoint, model, prompt: "#1: DUPLICATE\n#2: DUPLICATE")
    closed = []
    monkeypatch.setattr(h, "close_issue", lambda number, comment, dry_run: closed.append(number))
    group = [_issue(1, "First"), _issue(2, "Second")]
    handled = h.triage_group(group, "model", "endpoint", dry_run=True)
    assert closed == [2]
    assert handled == {2}


def test_triage_group_folds_multiple_fold_candidates_into_consolidator(monkeypatch):
    monkeypatch.setattr(h, "fetch_ollama_review", lambda endpoint, model, prompt: "#1: FOLD\n#2: FOLD")
    monkeypatch.setattr(h, "create_consolidator_issue", lambda title, folded, dry_run: 999)
    closed = []
    monkeypatch.setattr(h, "close_issue", lambda number, comment, dry_run: closed.append(number))
    group = [_issue(1, "First"), _issue(2, "Second")]
    handled = h.triage_group(group, "model", "endpoint", dry_run=True)
    assert closed == [1, 2]
    assert handled == {1, 2}


def test_triage_group_single_fold_candidate_is_left_unhandled(monkeypatch):
    monkeypatch.setattr(h, "fetch_ollama_review", lambda endpoint, model, prompt: "#1: FOLD")
    created = []
    monkeypatch.setattr(h, "create_consolidator_issue", lambda title, folded, dry_run: created.append(1))
    group = [_issue(1, "First")]
    handled = h.triage_group(group, "model", "endpoint", dry_run=True)
    assert created == []
    assert handled == set()


def test_triage_group_new_feature_is_commented_and_handled(monkeypatch):
    monkeypatch.setattr(h, "fetch_ollama_review", lambda endpoint, model, prompt: "#1: NEW_FEATURE")
    commented = []
    monkeypatch.setattr(h, "comment_new_feature", lambda number, dry_run: commented.append(number))
    group = [_issue(1, "Add a feature"), _issue(2, "Nit")]
    handled = h.triage_group(group, "model", "endpoint", dry_run=True)
    assert commented == [1]
    assert 1 in handled


def test_triage_remaining_assigns_milestone_to_backlog_issues(monkeypatch):
    monkeypatch.setattr(h, "classify_single_issue", lambda issue, model, endpoint: "BACKLOG")
    assigned = []
    monkeypatch.setattr(h, "assign_milestone", lambda number, milestone, dry_run: assigned.append(number))
    h.triage_remaining([_issue(1, "Nit")], "model", "endpoint", dry_run=True)
    assert assigned == [1]


def test_triage_remaining_skips_milestone_for_new_feature(monkeypatch):
    monkeypatch.setattr(h, "classify_single_issue", lambda issue, model, endpoint: "NEW_FEATURE")
    assigned = []
    commented = []
    monkeypatch.setattr(h, "assign_milestone", lambda number, milestone, dry_run: assigned.append(number))
    monkeypatch.setattr(h, "comment_new_feature", lambda number, dry_run: commented.append(number))
    h.triage_remaining([_issue(1, "Add a feature")], "model", "endpoint", dry_run=True)
    assert assigned == []
    assert commented == [1]
