"""Classify a PR's diff as "doc-only" so CI can skip heavyweight test jobs.

A change is doc-only when every changed line, across every changed file, is
one of: a blank line, a full-line comment in a language we recognise, or a
line inside a file matched by a documentation glob (``*.md``, ``docs/**``,
etc.). Anything else -- including a single line of real code, a config file
edit, a permission-bit change, or a rename that touches a non-doc path --
makes the whole diff non-doc-only.

The classifier is intentionally conservative: false negatives (running the
full suite on a change that was actually doc-only) are fine, false positives
(skipping the full suite on a change that touches real behaviour) are not.
When in doubt, this module says "not doc-only".

Usage::

    python scripts/classify_change.py --event-name pull_request \\
        --base <base-sha> --head <head-sha> [--github-output "$GITHUB_OUTPUT"]

Prints ``doc-only=true`` or ``doc-only=false`` to stdout and, if
``--github-output`` is given, appends the same line to that file so a GitHub
Actions step can expose it via ``steps.<id>.outputs.doc-only``.

This script intentionally uses only the Python standard library so it can
run in CI before any pip install step.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Only these extensions get per-line comment detection; every other
# extension is treated as unsafe (non-doc-only) the moment it changes at
# all, even if the change looks like a comment -- e.g. YAML/JSON/TOML/ini
# config files, which can affect runtime behaviour even via a "comment".
SAFE_COMMENT_PREFIXES: dict[str, tuple[str, ...]] = {
    ".py": ("#",),
    ".ts": ("//", "/*", "*/", "*"),
    ".tsx": ("//", "/*", "*/", "*"),
    ".js": ("//", "/*", "*/", "*"),
    ".jsx": ("//", "/*", "*/", "*"),
    ".mjs": ("//", "/*", "*/", "*"),
    ".cjs": ("//", "/*", "*/", "*"),
    ".mts": ("//", "/*", "*/", "*"),
    ".cts": ("//", "/*", "*/", "*"),
}

_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


class FileDiff:
    """Mutable record of one file's entry in a unified `git diff`."""

    def __init__(self, path: str, old_path: str) -> None:
        self.path = path
        self.old_path = old_path
        self.binary = False
        self.mode_change = False
        self.rename = False
        self.changed_lines: list[str] = []


def parse_file_diffs(diff_text: str) -> list[FileDiff]:
    """Split a unified `git diff` into per-file records.

    Only the `diff --git a/... b/...` header lines are trusted for paths
    (not `+++`/`---`, which read `/dev/null` for adds/deletes) so add/delete
    diffs still resolve to the file's real path.
    """
    files: list[FileDiff] = []
    current: FileDiff | None = None
    for line in diff_text.splitlines():
        header = _DIFF_HEADER_RE.match(line)
        if header:
            if current is not None:
                files.append(current)
            current = FileDiff(path=header.group(2), old_path=header.group(1))
            continue
        if current is None:
            continue
        if line.startswith("old mode") or line.startswith("new mode"):
            current.mode_change = True
        elif line.startswith("rename from ") or line.startswith("rename to "):
            current.rename = True
        elif line.startswith("Binary files"):
            current.binary = True
        elif line.startswith("@@") or line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+") or line.startswith("-"):
            current.changed_lines.append(line[1:])
    if current is not None:
        files.append(current)
    return files


def is_doc_path(path: str) -> bool:
    """Return True if *path* is documentation content, not executable/config."""
    normalised = path.lower()
    if normalised.endswith(".md"):
        return True
    if normalised.startswith("docs/") or "/docs/" in f"/{normalised}":
        return True
    if normalised.startswith(".github/issue_template/"):
        return True
    name = normalised.rsplit("/", 1)[-1]
    return name.startswith("license") or name.startswith("changelog")


def is_safe_line(content: str, comment_prefixes: tuple[str, ...]) -> bool:
    stripped = content.strip()
    if not stripped:
        return True
    return stripped.startswith(comment_prefixes)


def classify_file(file_diff: FileDiff) -> bool:
    """Return True if this file's changes cannot affect runtime behaviour."""
    doc_new = is_doc_path(file_diff.path)
    doc_old = is_doc_path(file_diff.old_path)
    # Checked ahead of the doc-path short-circuit below: a permission-bit
    # change carries no content diff, so a doc path alone can't vouch for
    # it being safe -- e.g. flipping docs/deploy.md to executable is still
    # a behavioural change worth running the full suite over.
    if file_diff.mode_change:
        return False
    if file_diff.rename:
        return doc_new and doc_old
    if doc_new:
        return True
    if file_diff.binary:
        return False
    comment_prefixes = SAFE_COMMENT_PREFIXES.get(Path(file_diff.path).suffix.lower())
    if comment_prefixes is None:
        return False
    return all(is_safe_line(line, comment_prefixes) for line in file_diff.changed_lines)


def classify_diff(diff_text: str) -> bool:
    """Return True if *diff_text* (a unified `git diff`) is doc-only."""
    files = parse_file_diffs(diff_text)
    return all(classify_file(f) for f in files)


def get_diff_text(base: str, head: str) -> str:
    result = subprocess.run(
        ["git", "diff", "--no-color", "--unified=0", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-name", default="", help="GitHub event name, e.g. 'pull_request'")
    parser.add_argument("--base", default="", help="Base ref/SHA to diff against")
    parser.add_argument("--head", default="", help="Head ref/SHA of the change")
    parser.add_argument("--github-output", default="", help="Path to $GITHUB_OUTPUT, if any")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Only pull_request events get diff-based classification; every other
    # event (push, workflow_dispatch, ...) conservatively runs the full
    # suite, since a base/head diff isn't meaningful in the same way there.
    doc_only = False
    if args.event_name == "pull_request" and args.base and args.head:
        try:
            diff_text = get_diff_text(args.base, args.head)
        except subprocess.CalledProcessError as exc:
            print(
                f"WARNING: could not compute diff ({exc}); treating as not doc-only",
                file=sys.stderr,
            )
        else:
            doc_only = classify_diff(diff_text)

    output_line = f"doc-only={'true' if doc_only else 'false'}"
    print(output_line)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write(output_line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
