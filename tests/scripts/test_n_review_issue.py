import json

import scripts.developer_tools.n_review_issue as n


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_parse_review_response_extracts_title_and_body():
    response = "TITLE: Fixed title\nBODY:\n## What\nUpdated content\n"
    title, body = n.parse_review_response(response, "old title", "old body")
    assert title == "Fixed title"
    assert body == "## What\nUpdated content"


def test_parse_review_response_falls_back_on_malformed_response():
    response = "I refuse to answer in the requested format."
    title, body = n.parse_review_response(response, "old title", "old body")
    assert (title, body) == ("old title", "old body")


def test_parse_review_response_falls_back_on_empty_body():
    response = "TITLE: New title\nBODY:\n"
    title, body = n.parse_review_response(response, "old title", "old body")
    assert (title, body) == ("old title", "old body")


def test_looks_like_content_loss_true_when_much_shorter():
    original = "## What\n" + ("detail line\n" * 50)
    revised = "## What\nshort"
    assert n.looks_like_content_loss(original, revised)


def test_looks_like_content_loss_false_when_similar_length():
    original = "## What\nsome detail here"
    revised = "## What\nsome updated detail here"
    assert not n.looks_like_content_loss(original, revised)


def test_looks_like_content_loss_false_when_original_is_empty():
    assert not n.looks_like_content_loss("", "")


def test_run_review_local_returns_none_when_ollama_unreachable(monkeypatch):
    monkeypatch.setattr(n, "validate_ollama_connection", lambda endpoint: False)
    assert n.run_review(n.LOCAL, "title", "body") is None


def test_run_review_local_returns_response(monkeypatch):
    monkeypatch.setattr(n, "validate_ollama_connection", lambda endpoint: True)
    monkeypatch.setattr(
        n, "fetch_ollama_review", lambda endpoint, model, prompt: "TITLE: t\nBODY:\nb"
    )
    assert n.run_review(n.LOCAL, "title", "body") == "TITLE: t\nBODY:\nb"


def test_run_review_cloud_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert n.run_review(n.CLOUD, "title", "body") is None


def test_run_review_cloud_returns_response(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    monkeypatch.setattr(n, "fetch_deepseek_review", lambda api_key, prompt: "TITLE: t\nBODY:\nb")
    assert n.run_review(n.CLOUD, "title", "body") == "TITLE: t\nBODY:\nb"


def test_run_review_returns_none_on_empty_response(monkeypatch):
    monkeypatch.setattr(n, "validate_ollama_connection", lambda endpoint: True)
    monkeypatch.setattr(n, "fetch_ollama_review", lambda endpoint, model, prompt: "   ")
    assert n.run_review(n.LOCAL, "title", "body") is None


def test_fetch_issue_parses_gh_json(monkeypatch):
    payload = json.dumps({"number": 42, "title": "T", "body": "B", "state": "OPEN", "url": "u"})
    monkeypatch.setattr(
        n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=0, stdout=payload)
    )
    issue = n.fetch_issue("owner", "repo", 42)
    assert issue == {"number": 42, "title": "T", "body": "B", "state": "OPEN", "url": "u"}


def test_fetch_issue_exits_on_gh_failure(monkeypatch):
    monkeypatch.setattr(
        n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=1, stderr="not found")
    )
    try:
        n.fetch_issue("owner", "repo", 42)
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert exc.code == 1


def test_update_issue_dry_run_skips_gh_call(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("gh should not be called in dry-run mode")

    monkeypatch.setattr(n.subprocess, "run", fail_if_called)
    assert n.update_issue("owner", "repo", 1, "title", "body", dry_run=True) is True


def test_update_issue_reports_failure(monkeypatch):
    monkeypatch.setattr(
        n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=1, stderr="boom")
    )
    assert n.update_issue("owner", "repo", 1, "title", "body", dry_run=False) is False


def test_update_issue_success(monkeypatch):
    monkeypatch.setattr(n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=0))
    assert n.update_issue("owner", "repo", 1, "title", "body", dry_run=False) is True
