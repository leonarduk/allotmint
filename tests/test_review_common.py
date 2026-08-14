from __future__ import annotations

import pytest
from cicaid_devtools.lib import review_common
from cicaid_devtools.lib.verdict import is_soft_skip


@pytest.mark.parametrize("provider", ["Claude", "GPT", "DeepSeek"])
def test_emit_empty_diff_notice_returns_success(provider) -> None:
    assert review_common.emit_empty_diff_notice(provider) == 0


@pytest.mark.parametrize("provider", ["Claude", "GPT", "DeepSeek"])
def test_emit_empty_diff_notice_parses_as_soft_skip(capsys, provider) -> None:
    """The empty-diff advisory notice must contain a soft-skip marker so
    extract_verdict.py treats it as "no review performed" rather than
    "no valid verdict found" (which the workflow's check_approval step
    otherwise reports as CHANGES REQUESTED — see #5715/#5721).
    """
    review_common.emit_empty_diff_notice(provider)
    notice = capsys.readouterr().out

    assert review_common.EMPTY_DIFF_MARKER in notice
    assert is_soft_skip(notice) == "empty diff"


@pytest.mark.parametrize("provider", ["Claude", "GPT", "DeepSeek"])
def test_genuine_request_changes_verdict_fails_workflow(capsys, tmp_path, provider) -> None:
    """A real, non-empty REQUEST CHANGES review must still fail the workflow
    via the verdict module.

    Mirrors the actual ``_ai-pr-review.yml`` pipeline: ``finalize_review``
    prints the model's review text to stdout (which the workflow redirects
    into a file), and a *separate* step later runs the verdict module
    against that file to decide the job's exit code.
    """
    review_text = (
        "### 1. Acceptance criteria\n"
        "Not fully met — see bug below.\n\n"
        "### 2. Bugs and logic errors\n"
        "Unhandled exception when the input list is empty (line 42).\n\n"
        "**REQUEST CHANGES** — fix the empty-list edge case before merging"
    )

    assert review_common.finalize_review(review_text, provider) == 0
    printed_review = capsys.readouterr().out

    review_file = tmp_path / "review.md"
    review_file.write_text(printed_review, encoding="utf-8")

    from cicaid_devtools.lib.verdict import main as verdict_main

    result = verdict_main(str(review_file), provider)

    assert result == 1
    captured = capsys.readouterr()
    assert f"[-] {provider} review: CHANGES REQUESTED" in captured.out


@pytest.mark.parametrize("provider", ["Claude", "GPT", "DeepSeek"])
def test_finalize_review_soft_skips_on_empty_review(capsys, provider) -> None:
    """Empty provider responses now soft-skip rather than hard-failing."""
    assert review_common.finalize_review("", provider) == 0
    output = capsys.readouterr().out
    assert review_common.EMPTY_REVIEW_MARKER in output
