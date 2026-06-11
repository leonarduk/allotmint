"""Tests for extract_followups.py."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from extract_followups import extract_followups


def test_extracts_titles_from_section_5() -> None:
    review = """\
## 5. Suggested follow-up issues

- Add unit tests for the new helper
- Refactor the auth module

**APPROVE**
"""
    assert extract_followups(review) == [
        "Add unit tests for the new helper",
        "Refactor the auth module",
    ]


def test_verdict_as_bullet_not_extracted() -> None:
    """Verdict line appearing as a bullet (- **APPROVE**) must not become a title.

    Regression test for https://github.com/leonarduk/allotmint/issues/3376 where
    the section-5 stop regex only matched **APPROVE** at line-start, so a bullet
    like '- **APPROVE**' bypassed the guard and was used as an issue title.
    """
    review = """\
## 5. Suggested follow-up issues

- Do some cleanup

- **APPROVE**
"""
    titles = extract_followups(review)
    assert "**APPROVE**" not in titles
    assert titles == ["Do some cleanup"]


def test_request_changes_as_bullet_not_extracted() -> None:
    review = """\
## 5. Suggested follow-up issues

- Fix the bug

- **REQUEST CHANGES**
"""
    titles = extract_followups(review)
    assert "**REQUEST CHANGES**" not in titles
    assert titles == ["Fix the bug"]


def test_no_section_5_returns_empty() -> None:
    review = "## 1. Summary\n\nLooks good.\n\n**APPROVE**\n"
    assert extract_followups(review) == []


def test_verdict_line_stops_section_extraction() -> None:
    review = """\
## 5. Suggested follow-up issues

- Valid follow-up

**APPROVE**

- Should not be included
"""
    assert extract_followups(review) == ["Valid follow-up"]


def test_generic_title_without_reference_is_dropped() -> None:
    """Vague 'more detailed/descriptive ... for clarity' titles with no concrete
    reference are noise (e.g. https://github.com/leonarduk/allotmint/issues/3641)
    and should not become issues."""
    review = """\
## 5. Suggested follow-up issues

- Consider adding more detailed comments in the test cases for clarity on what each test is validating.
- Add unit tests for the new helper

**APPROVE**
"""
    assert extract_followups(review) == ["Add unit tests for the new helper"]


def test_generic_phrasing_with_reference_is_kept() -> None:
    """A generic-sounding suggestion is kept if it names a concrete file/function."""
    review = """\
## 5. Suggested follow-up issues

- Consider adding more descriptive comments in `create_followup_issues.py` for clarity on the label assignment logic.

**APPROVE**
"""
    assert extract_followups(review) == [
        "Consider adding more descriptive comments in `create_followup_issues.py` for clarity on the label assignment logic."
    ]


def test_specific_title_is_kept() -> None:
    review = """\
## 5. Suggested follow-up issues

- Refactor `extract_followups` to split the section-search logic into a helper

**APPROVE**
"""
    assert extract_followups(review) == [
        "Refactor `extract_followups` to split the section-search logic into a helper"
    ]
