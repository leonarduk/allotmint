"""Classify a PR's diff so CI runs only the test jobs the change can affect.

Two classifications are produced from a single ``git diff``:

``doc-only``
    True when every changed line, across every changed file, is one of: a
    blank line, a full-line comment in a language we recognise, or a line
    inside a file matched by a documentation glob (``*.md``, ``docs/**``,
    etc.). Anything else -- including a single line of real code, a config
    file edit, a permission-bit change, or a rename that touches a non-doc
    path -- makes the whole diff non-doc-only.

``backend`` / ``frontend`` / ``cdk`` / ``shell``
    Per-area flags derived from the changed *paths* via ``AREA_PATH_RULES``
    below. A doc-only diff sets every area to false, so CI jobs need to
    consult one flag rather than a flag plus a doc-only override.

``backend-dev-tools-only``
    True when the backend area is affected *and* every backend-affecting
    path is confined to ``tests/scripts/**`` -- local-only script tests
    with no import relationship to ``backend/``. Not an area gate on its
    own: it only tells the backend job it can run ``tests/scripts``
    instead of the full suite.

The classifier is intentionally conservative: false negatives (running a
suite that the change could not have broken) are cheap, false positives
(skipping a suite that would have caught a regression) are not. When in
doubt -- an unrecognised path, a failed diff, a non-``pull_request`` event --
this module widens to "everything is affected".

Usage::

    python scripts/classify_change.py --event-name pull_request \\
        --base <base-sha> --head <head-sha> [--github-output "$GITHUB_OUTPUT"]

Prints one ``key=value`` line per flag to stdout and, if ``--github-output``
is given, appends the same lines to that file so a GitHub Actions step can
expose them via ``steps.<id>.outputs.<key>``.

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

# Every CI area a change can affect. Adding an area here is not enough on its
# own -- it also needs a rule in AREA_PATH_RULES and a job gated on it.
AREAS: tuple[str, ...] = ("backend", "frontend", "cdk", "shell")

_ALL_AREAS = frozenset(AREAS)
_NO_AREAS: frozenset[str] = frozenset()

# Ordered path -> area map. The FIRST rule whose glob matches a changed path
# decides that path's areas; later rules are not consulted. Order therefore
# matters: narrow rules must precede the broad ones they sit inside (e.g.
# `tests/bash/**` before `tests/**`).
#
# Globs are matched case-insensitively against forward-slash repo-relative
# paths. `**` matches across directory separators, `*` does not.
#
# A path matching NO rule falls back to "every area" -- see areas_for_path.
# That fallback is what keeps a newly added top-level directory from silently
# skipping every suite, so resist the urge to add a catch-all rule here.
AREA_PATH_RULES: tuple[tuple[str, frozenset[str]], ...] = (
    # -- Documentation: affects no executable area. ------------------------
    ("docs/**", _NO_AREAS),
    ("**/*.md", _NO_AREAS),
    (".github/issue_template/**", _NO_AREAS),
    (".github/pull_request_template*", _NO_AREAS),
    ("license*", _NO_AREAS),
    # -- CI's own machinery: widen to everything. --------------------------
    # A workflow, composite action, ruleset or classifier edit can change the
    # behaviour of any job, including this gating itself, so such a change
    # must never narrow the suite that validates it.
    ("scripts/classify_change.py", _ALL_AREAS),
    ("scripts/check_branch_protection_required_checks.py", _ALL_AREAS),
    ("scripts/check_live_branch_protection.py", _ALL_AREAS),
    (".github/**", _ALL_AREAS),
    # -- Shell / container / deploy tooling. -------------------------------
    ("scripts/bash/**", frozenset({"shell"})),
    ("**/*.sh", frozenset({"shell"})),
    ("**/*.bats", frozenset({"shell"})),
    ("tests/bash/**", frozenset({"shell"})),
    ("dockerfile*", frozenset({"shell"})),
    ("**/dockerfile*", frozenset({"shell"})),
    ("docker/**", frozenset({"shell"})),
    ("docker-compose*.yml", frozenset({"shell"})),
    ("deploy/**", frozenset({"shell"})),
    ("jenkinsfile*", frozenset({"shell"})),
    # -- Frontend. ---------------------------------------------------------
    ("frontend/**", frozenset({"frontend"})),
    # The root package.json/lockfile installs the CDK CLI used by cdk synth
    # (`../node_modules/.bin/cdk`) as well as the repo-level npm scripts, so a
    # change there is both a frontend and a CDK concern.
    ("package.json", frozenset({"frontend", "cdk"})),
    ("package-lock.json", frozenset({"frontend", "cdk"})),
    # -- Infrastructure. ---------------------------------------------------
    # Deliberately does NOT include backend/** or frontend/**: cdk/tests are
    # unit tests over CDK constructs, which application code cannot break.
    # The full synth-against-real-assets path stays covered by cdk-dry-run.yml,
    # whose own `paths:` filter still lists backend/** and frontend/**.
    ("cdk/**", frozenset({"cdk"})),
    ("infra/**", frozenset({"cdk"})),
    # -- Backend. ----------------------------------------------------------
    # The SPA contract version is asserted on both sides of the wire by
    # scripts/check_contract_version_sync.py, so this one module is a
    # frontend concern too.
    ("backend/contracts_spa.py", frozenset({"backend", "frontend"})),
    # trading_agent.py's checks_skipped vocabulary is asserted against
    # frontend copy by frontend/tests/unit/pages/Trading.test.tsx (#7230) --
    # a backend-only PR that changes it must still run the frontend suite,
    # or the drift-detecting test only fires later on an unrelated PR.
    ("backend/agent/trading_agent.py", frozenset({"backend", "frontend"})),
    ("backend/**", frozenset({"backend"})),
    ("tests/**", frozenset({"backend"})),
    ("data/**", frozenset({"backend"})),
    ("requirements*.txt", frozenset({"backend"})),
    ("pyproject.toml", frozenset({"backend"})),
    ("pytest.ini", frozenset({"backend"})),
    ("mypy.ini", frozenset({"backend"})),
    ("logging.ini", frozenset({"backend"})),
    ("config*.yaml", frozenset({"backend"})),
    ("makefile", frozenset({"backend"})),
    # Remaining scripts/ entries are Python helpers covered by tests/scripts.
    ("scripts/**", frozenset({"backend"})),
)


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a repo-path glob to a regex.

    `**/` matches zero or more leading directories, `**` matches across
    separators, `*` matches within a single path segment.
    """
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile("^" + "".join(parts) + "$")


_COMPILED_AREA_RULES: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = tuple(
    (_glob_to_regex(pattern), areas) for pattern, areas in AREA_PATH_RULES
)


def areas_for_path(path: str) -> frozenset[str]:
    """Return the CI areas a single changed *path* can affect.

    Falls back to every area when no rule matches, so an unmapped path can
    never cause a suite to be skipped.
    """
    normalised = path.lower()
    for regex, areas in _COMPILED_AREA_RULES:
        if regex.match(normalised):
            return areas
    return _ALL_AREAS


# Paths whose only backend-relevant coverage lives in `tests/scripts/`: the
# local-only script tests, which are not imported by `backend/`.
# When every backend-affecting path in a diff matches one of these globs,
# `backend-integration.yml` can run `pytest tests/scripts` instead of the
# full backend suite -- see issue #5823.
_NARROW_BACKEND_GLOBS: tuple[str, ...] = ("tests/scripts/**",)
_COMPILED_NARROW_BACKEND_RULES: tuple[re.Pattern[str], ...] = tuple(
    _glob_to_regex(pattern) for pattern in _NARROW_BACKEND_GLOBS
)


def _is_narrow_backend_path(path: str) -> bool:
    normalised = path.lower()
    return any(regex.match(normalised) for regex in _COMPILED_NARROW_BACKEND_RULES)


def backend_dev_tools_only(diff_text: str) -> bool:
    """Return True if every backend-affecting path is confined to dev-tools.

    False whenever the backend area isn't touched at all -- callers must only
    consult this after confirming the backend area flag is true, mirroring
    how doc-only zeroes every area rather than this flag standing alone.
    """
    saw_backend_path = False
    for file_diff in parse_file_diffs(diff_text):
        for path in (file_diff.path, file_diff.old_path):
            if "backend" not in areas_for_path(path):
                continue
            saw_backend_path = True
            if not _is_narrow_backend_path(path):
                return False
    return saw_backend_path


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
    # it being safe -- e.g. flipping docs/DEPLOY.md to executable is still
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


def areas_for_diff(diff_text: str) -> frozenset[str]:
    """Return the union of CI areas affected by *diff_text*.

    Renames contribute both their old and new path, so moving a file out of
    an area still runs that area's suite.
    """
    affected: set[str] = set()
    for file_diff in parse_file_diffs(diff_text):
        affected |= areas_for_path(file_diff.path)
        if file_diff.old_path != file_diff.path:
            affected |= areas_for_path(file_diff.old_path)
    return frozenset(affected)


def classify(event_name: str, base: str, head: str) -> tuple[bool, frozenset[str], bool]:
    """Return ``(doc_only, affected_areas, backend_dev_tools_only)`` for a change.

    Only ``pull_request`` events get diff-based classification; every other
    event (push, workflow_dispatch, ...) conservatively runs the full suite,
    since a base/head diff isn't meaningful in the same way there. A diff
    that cannot be computed widens to the full suite for the same reason --
    both fall back to ``backend_dev_tools_only=False`` so the backend job
    runs its full suite rather than the narrow one.
    """
    if event_name != "pull_request" or not base or not head:
        return False, _ALL_AREAS, False
    try:
        diff_text = get_diff_text(base, head)
    except subprocess.CalledProcessError as exc:
        print(
            f"WARNING: could not compute diff ({exc}); treating every area as affected",
            file=sys.stderr,
        )
        return False, _ALL_AREAS, False
    # A doc-only diff zeroes every area so gated jobs consult a single flag
    # rather than an area flag plus a doc-only override.
    if classify_diff(diff_text):
        return True, _NO_AREAS, False
    areas = areas_for_diff(diff_text)
    narrow = "backend" in areas and backend_dev_tools_only(diff_text)
    return False, areas, narrow


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


def format_output_lines(doc_only: bool, areas: frozenset[str], backend_dev_tools_only: bool) -> list[str]:
    """Render the classification as ``key=value`` lines, doc-only first.

    ``backend-dev-tools-only`` is not an area gate -- it never skips a job on
    its own -- so it's appended last, after every area flag.
    """
    lines = [f"doc-only={'true' if doc_only else 'false'}"]
    lines.extend(f"{area}={'true' if area in areas else 'false'}" for area in AREAS)
    lines.append(f"backend-dev-tools-only={'true' if backend_dev_tools_only else 'false'}")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    doc_only, areas, backend_dev_tools_only = classify(args.event_name, args.base, args.head)

    output_lines = format_output_lines(doc_only, areas, backend_dev_tools_only)
    for line in output_lines:
        print(line)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write("\n".join(output_lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
