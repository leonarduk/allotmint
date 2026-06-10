#!/usr/bin/env python3
"""Fail if a `cdk diff --method=changeset` run removes an IAM Allow statement
for the GitHub deploy role (or other watched resources) without an equivalent
replacement.

`cdk diff` exits 0 even when its "IAM Statement Changes" table shows an
``Allow`` statement being removed, so a removed grant for the deploy role
(e.g. `lambda:InvokeFunction` on `PriceRefreshLambdaLiveAlias`, or `s3:GetObject`
on `PortfolioDataBucket`) would otherwise pass `pre-deploy-check` silently. See #3741.

Usage:
    python scripts/check_cdk_diff_iam_removals.py [diff_output_file]

Reads the diff output from the given file, or from stdin if no file is given.
Exits 1 and prints the offending rows if an unmatched removal is found.
"""

from __future__ import annotations

import re
import sys

IAM_TABLE_HEADER = "IAM Statement Changes"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

# Substrings (matched case-insensitively against a removed row's cells) that
# identify a statement as belonging to the GitHub deploy role's grants.
DEFAULT_WATCH_PATTERNS = (
    "github-deploy",
    "GithubDeployRole",
    "PriceRefreshLambda",
    "PortfolioDataBucket",
)


def _table_row_cells(line: str) -> list[str] | None:
    """Split a `│ a │ b │ c │`-style table row into trimmed cells.

    Returns None for lines that aren't a `│`-delimited row (borders, blank
    lines, or text outside the table).
    """
    stripped = line.strip()
    if not stripped.startswith("│") or not stripped.endswith("│"):
        return None
    return [cell.strip() for cell in stripped.strip("│").split("│")]


def find_iam_statement_rows(diff_output: str) -> list[list[str]]:
    """Return data rows from any "IAM Statement Changes" table in `diff_output`.

    Each row is `[marker, resource, effect, action, principal, condition]`
    where `marker` is `+`, `-`, or empty. The column-header row itself is
    skipped.
    """
    rows: list[list[str]] = []
    in_table = False
    for raw_line in diff_output.splitlines():
        line = ANSI_ESCAPE_RE.sub("", raw_line)
        if IAM_TABLE_HEADER in line:
            in_table = True
            continue
        if not in_table:
            continue
        cells = _table_row_cells(line)
        if cells is None:
            # A non-table line (other than a border) ends this table.
            if not line.strip().startswith(("┌", "├", "└", "┬", "┼", "┴")):
                in_table = False
            continue
        if "Effect" in cells and "Action" in cells:
            continue  # column-header row
        rows.append(cells)
    return rows


def find_unmatched_allow_removals(
    diff_output: str, watch_patterns: tuple[str, ...] = DEFAULT_WATCH_PATTERNS
) -> list[list[str]]:
    """Return removed `Allow` statement rows matching `watch_patterns` that
    have no identical addition elsewhere in the diff (i.e. a net removal,
    not a destroy+create replacement that nets out unchanged)."""
    rows = find_iam_statement_rows(diff_output)
    removed = [r for r in rows if r and r[0] == "-"]
    added = [r for r in rows if r and r[0] == "+"]
    added_signatures = {tuple(r[1:]) for r in added}

    unmatched: list[list[str]] = []
    for row in removed:
        if tuple(row[1:]) in added_signatures:
            continue
        effect = row[2] if len(row) > 2 else ""
        if effect.lower() != "allow":
            continue
        row_text = " ".join(row)
        if any(re.search(pat, row_text, re.IGNORECASE) for pat in watch_patterns):
            unmatched.append(row)
    return unmatched


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        diff_output = open(argv[1], encoding="utf-8", errors="replace").read()
    else:
        diff_output = sys.stdin.read()

    unmatched = find_unmatched_allow_removals(diff_output)
    if not unmatched:
        return 0

    print(
        "ERROR: cdk diff removes the following IAM 'Allow' statement(s) for the "
        "GitHub deploy role (or other watched resources) with no matching "
        "addition elsewhere in the diff:",
        file=sys.stderr,
    )
    for row in unmatched:
        print(f"  - {row}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
