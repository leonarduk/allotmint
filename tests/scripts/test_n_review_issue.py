"""Tests for the bounded issue-review feedback compatibility entry point."""

from unittest.mock import Mock

from scripts.developer_tools import n_review_issue


def test_limited_disposition_prompt_aborts_after_maximum_feedback(monkeypatch) -> None:
    prompt = Mock(return_value=("retry", "try again"))
    log_error = Mock()
    monkeypatch.setattr(n_review_issue.review_issue.logger, "error", log_error)
    limited_prompt = n_review_issue.limited_disposition_prompt(prompt)

    for _ in range(n_review_issue.MAX_FEEDBACK_RETRIES):
        assert limited_prompt() == ("retry", "try again")

    assert limited_prompt() == ("abort", None)
    assert prompt.call_count == n_review_issue.MAX_FEEDBACK_RETRIES + 1
    log_error.assert_called_once_with("Maximum feedback retries reached; aborting without applying the review.")


def test_limited_disposition_prompt_preserves_apply_and_abort() -> None:
    prompt = Mock(side_effect=[("apply", None), ("abort", None)])
    limited_prompt = n_review_issue.limited_disposition_prompt(prompt)

    assert limited_prompt() == ("apply", None)
    assert limited_prompt() == ("abort", None)


def test_main_restores_shared_prompt(monkeypatch) -> None:
    original_prompt = n_review_issue.review_issue.prompt_for_disposition
    shared_main = Mock(return_value=0)
    monkeypatch.setattr(n_review_issue.review_issue, "main", shared_main)

    assert n_review_issue.main() == 0

    shared_main.assert_called_once_with()
    assert n_review_issue.review_issue.prompt_for_disposition is original_prompt
