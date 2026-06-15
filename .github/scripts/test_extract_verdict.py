"""Unit tests for extract_verdict.py."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

# Add the scripts directory to the Python path so we can import extract_verdict
sys.path.insert(0, str(Path(__file__).parent))

from extract_verdict import extract_verdict


class TestExtractVerdict:
    """Test the extract_verdict function with various verdict formats."""

    def test_plain_approve(self) -> None:
        """Test plain **APPROVE** format."""
        review_text = """
## Review

Some analysis here.

**APPROVE** — no blocking concerns
"""
        assert extract_verdict(review_text) == "APPROVE"

    def test_plain_request_changes(self) -> None:
        """Test plain **REQUEST CHANGES** format."""
        review_text = """
## Review

Found an issue.

**REQUEST CHANGES** — blocking bug on line 42
"""
        assert extract_verdict(review_text) == "REQUEST CHANGES"

    def test_backtick_wrapped_approve(self) -> None:
        """Test backtick-wrapped **`APPROVE`** format (DeepSeek variant)."""
        review_text = """
## Review

Everything looks good.

**`APPROVE`** — no blocking concerns
"""
        assert extract_verdict(review_text) == "APPROVE"

    def test_backtick_wrapped_request_changes(self) -> None:
        """Test backtick-wrapped **`REQUEST CHANGES`** format."""
        review_text = """
## Review

Found blocking issues.

**`REQUEST CHANGES`** — unhandled edge case
"""
        assert extract_verdict(review_text) == "REQUEST CHANGES"

    def test_verdict_in_middle_of_text(self) -> None:
        """Test that verdict is found even when surrounded by other text."""
        review_text = """
### 1. Acceptance criteria
Looks good.

### 2. Bugs
None found.

**APPROVE** — ready to merge

Some closing thoughts.
"""
        assert extract_verdict(review_text) == "APPROVE"

    def test_backtick_wrapped_in_middle_of_text(self) -> None:
        """Test backtick-wrapped verdict in middle of review."""
        review_text = """
### Analysis

All sections reviewed.

**`APPROVE`** — no blockers

Final note: great work!
"""
        assert extract_verdict(review_text) == "APPROVE"

    def test_no_verdict(self) -> None:
        """Test that None is returned when no valid verdict is found."""
        review_text = """
## Review

Some analysis here with no verdict line.

Looks good overall.
"""
        assert extract_verdict(review_text) is None

    def test_empty_string(self) -> None:
        """Test that None is returned for empty input."""
        assert extract_verdict("") is None

    def test_whitespace_only(self) -> None:
        """Test that None is returned for whitespace-only input."""
        assert extract_verdict("   \n\n   ") is None

    def test_verdict_with_extra_context(self) -> None:
        """Test verdict extraction with full review context."""
        review_text = """
## Acceptance criteria
All criteria met.

## Bugs and logic errors
None found.

## API, data, and workflow safety
No issues.

## Test coverage
Tests cover the new functionality.

**APPROVE** — no blocking concerns (non-blocking items go in section 5 above)
"""
        assert extract_verdict(review_text) == "APPROVE"

    def test_backtick_variant_with_full_context(self) -> None:
        """Test backtick variant with full review context."""
        review_text = """
## Acceptance criteria
AC met.

## Bugs
Found one.

**`REQUEST CHANGES`** — unhandled exception at line 123
"""
        assert extract_verdict(review_text) == "REQUEST CHANGES"

    def test_case_sensitivity(self) -> None:
        """Test that verdict matching is case-sensitive (reject lowercase)."""
        review_text = "**approve** — no issues"
        assert extract_verdict(review_text) is None

    def test_partial_verdict_no_match(self) -> None:
        """Test that incomplete verdict formats don't match."""
        review_text = "APPROVE — no issues"  # missing bold markers
        assert extract_verdict(review_text) is None

    def test_single_backtick_malformed_format_matches(self) -> None:
        """Test that the regex matches a single-backtick malformed format (e.g., **`APPROVE**)."""
        review_text = "**`APPROVE** — missing closing backtick"
        verdict = extract_verdict(review_text)
        assert verdict == "APPROVE"

    def test_multiple_verdicts_returns_first(self) -> None:
        """Test that when multiple verdicts appear, the first one is returned."""
        review_text = """
Initial analysis: **APPROVE** — looks good

Wait, I found an issue: **REQUEST CHANGES** — blocking bug
"""
        assert extract_verdict(review_text) == "APPROVE"


class TestExtractVerdictScriptMain:
    """Test the main() function when called via the script."""

    def test_main_with_approve_verdict(self) -> None:
        """Test main() returns 0 for APPROVE verdict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("**APPROVE** — no issues")
            f.flush()
            temp_path = f.name

        try:
            result = subprocess.run(
                ["python3", ".github/scripts/extract_verdict.py", temp_path, "TestProvider"],
                cwd="/mnt/c/Users/steph/workspace/GitHub/allotmint" if Path("/mnt/c/Users/steph/workspace/GitHub/allotmint").exists() else "C:\\Users\\steph\\workspace\\GitHub\\allotmint",
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0
            assert "APPROVED" in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_main_with_request_changes_verdict(self) -> None:
        """Test main() returns 1 for REQUEST CHANGES verdict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("**REQUEST CHANGES** — blocking issue")
            f.flush()
            temp_path = f.name

        try:
            result = subprocess.run(
                ["python3", ".github/scripts/extract_verdict.py", temp_path, "TestProvider"],
                cwd="/mnt/c/Users/steph/workspace/GitHub/allotmint" if Path("/mnt/c/Users/steph/workspace/GitHub/allotmint").exists() else "C:\\Users\\steph\\workspace\\GitHub\\allotmint",
                capture_output=True,
                text=True,
            )
            assert result.returncode == 1
            assert "CHANGES REQUESTED" in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_main_with_backtick_approve(self) -> None:
        """Test main() returns 0 for backtick-wrapped APPROVE."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("**`APPROVE`** — no issues")
            f.flush()
            temp_path = f.name

        try:
            result = subprocess.run(
                ["python3", ".github/scripts/extract_verdict.py", temp_path, "DeepSeek"],
                cwd="/mnt/c/Users/steph/workspace/GitHub/allotmint" if Path("/mnt/c/Users/steph/workspace/GitHub/allotmint").exists() else "C:\\Users\\steph\\workspace\\GitHub\\allotmint",
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0
            assert "APPROVED" in result.stdout
        finally:
            Path(temp_path).unlink()

    def test_main_with_no_verdict(self) -> None:
        """Test main() returns 1 when no valid verdict found."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("Some review text without a verdict line.")
            f.flush()
            temp_path = f.name

        try:
            result = subprocess.run(
                ["python3", ".github/scripts/extract_verdict.py", temp_path, "TestProvider"],
                cwd="/mnt/c/Users/steph/workspace/GitHub/allotmint" if Path("/mnt/c/Users/steph/workspace/GitHub/allotmint").exists() else "C:\\Users\\steph\\workspace\\GitHub\\allotmint",
                capture_output=True,
                text=True,
            )
            assert result.returncode == 1
            assert "did not include a valid verdict" in result.stderr
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
