"""Tests for .github/scripts/filter_followups.py (only real-gap AI-review follow-ups are filed)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "filter_followups.py"
_spec = importlib.util.spec_from_file_location("filter_followups", SCRIPT)
assert _spec and _spec.loader
filter_followups = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filter_followups)

REVIEW = """## 4. Test coverage

- [nit] this bullet is outside the follow-ups section and must stay.

## 5. Suggested follow-up issues (optional)

- [gap] Roll back an import's rows by content so a concurrent delete can't remove other rows.
- [nit] Add a test for the moversUnavailable branch.
- [gap] Add a brief comment explaining the boundary.
- Normalise both sides of the account comparison.
- [GAP] Guard `_alert_text` against a missing month and return a 404 instead of a 500.
  The month can be None when the pension has no carry-forward.
- [nit] Rename `_recover_failed_save`.
  It reads backwards.

- `**APPROVE**` — ACs met.

---
*Reviewed by DeepSeek.*
"""


def test_keeps_only_gap_follow_ups_and_strips_their_tags():
    filtered, kept = filter_followups.filter_review(REVIEW)

    assert kept == 2
    assert "- Roll back an import's rows by content" in filtered
    assert "- Guard `_alert_text` against a missing month" in filtered
    assert "  The month can be None when the pension has no carry-forward." in filtered
    assert "[gap]" not in filtered.lower()


def test_drops_nit_untagged_and_nit_worded_gap_bullets_with_their_continuations():
    filtered, _ = filter_followups.filter_review(REVIEW)

    assert "moversUnavailable" not in filtered
    assert "brief comment" not in filtered
    assert "Normalise both sides" not in filtered
    assert "_recover_failed_save" not in filtered
    assert "It reads backwards." not in filtered


def test_leaves_the_verdict_and_other_sections_untouched():
    filtered, _ = filter_followups.filter_review(REVIEW)

    assert "- [nit] this bullet is outside the follow-ups section and must stay." in filtered
    assert "- `**APPROVE**` — ACs met." in filtered
    assert filtered.rstrip().endswith("*Reviewed by DeepSeek.*")


@pytest.mark.parametrize(
    "text",
    [
        "[gap] Consider caching the journal per owner.",
        "[gap] Document why the boundary is inclusive.",
        "[gap] Add an inline comment near the hook call.",
        "[gap] Update the docstring to match.",
        "[gap] Reword the race comment.",
    ],
)
def test_gap_tag_does_not_rescue_nit_wording(text):
    assert filter_followups.classify(text)[0] is False


@pytest.mark.parametrize(
    "text",
    [
        "[gap] Re-check the holdings document under the lock before appending.",
        "[gap] Name the missing column in the skip reason so imports can be fixed.",
        "[gap] Add a test that a failed S3 read never overwrites goals.",
    ],
)
def test_real_gaps_mentioning_similar_words_are_kept(text):
    assert filter_followups.classify(text)[0] is True


def test_a_review_without_a_follow_ups_section_is_unchanged():
    body = "## 1. Acceptance criteria\n\nAll met.\n\n**APPROVE**\n"

    assert filter_followups.filter_review(body) == (body, 0)


def test_cli_writes_the_filtered_review_and_prints_the_count(tmp_path):
    src, out = tmp_path / "review.md", tmp_path / "filtered.md"
    src.write_text(REVIEW, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(src), str(out)], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "2"
    assert out.read_text(encoding="utf-8") == filter_followups.filter_review(REVIEW)[0]
