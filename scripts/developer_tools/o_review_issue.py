"""CLI tool to review and refresh a single GitHub issue using a local or cloud LLM.

Continues the a_/b_/c_/.../o_ script chain in scripts/developer_tools/. Fetches one
issue by number, asks the chosen model (local Ollama or cloud DeepSeek) to bring the
title/body up to date, shows a diff of the proposed change, and only calls `gh issue
edit` after the user approves it. Never touches the issue if the model's answer looks
like it dropped content from the original.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Add the local lib/ dir (for github_repo/llm_common) to sys.path so this
# works both as an importable module and when invoked directly, where the
# repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).parent / "lib"))
from github_repo import get_repo_info, get_repo_root  # noqa: E402
from issue_review import parse_review_response  # noqa: E402
from llm_common import (  # noqa: E402
    CLOUD,
    LOCAL,
    describe_model_source,
    fetch_review,
    prompt_for_model_source,
    validate_model_source,
)

REPO_ROOT_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


def load_env_file(env_path: Path = REPO_ROOT_ENV_FILE) -> None:
    """Load local dev secrets (e.g. DEEPSEEK_API_KEY) from a repo-root .env file.

    CI sets these as real env vars instead, so a missing .env or missing
    python-dotenv is fine -- this only helps local, interactive runs.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path)


load_env_file()

# Below this fraction of the original body length, treat the model's answer as having
# dropped content rather than genuinely trimmed stale text, and refuse to show it as a
# safe-to-approve diff.
MIN_BODY_LENGTH_RATIO = 0.5

# Canonical issue structure: the bug report template is the source of truth for the
# section headings the model must produce, so a template edit propagates here without
# a matching code change.
BUG_REPORT_TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent / ".github" / "ISSUE_TEMPLATE" / "bug_report.md"
)
FALLBACK_TEMPLATE_SECTIONS = [
    "What",
    "Why",
    "How",
    "Files Affected",
    "Constraints",
    "LLM tier",
    "Success looks like",
    "Failure looks like",
]

REVIEW_PROMPT_TEMPLATE = """You are reviewing an existing GitHub issue from the allotmint repo \
for staleness before it is worked on. The issue may describe files, behaviour, or context that \
has since changed.

Update the title and body so they are accurate and current. The issue must use this section \
structure, taken from .github/ISSUE_TEMPLATE/bug_report.md: {sections}. Add any of these \
sections that are missing from the original issue (with a best-effort value inferred from the \
rest of the issue, or "Unknown" if it can't be inferred), and keep every concrete detail that \
is still accurate. Never delete information outright -- if something is now uncertain, flag it \
inline instead of removing it. Do not invent new requirements or acceptance criteria that \
aren't implied by the original text.

You do not have direct access to the repository, so for the 'Files Affected' section only use \
paths listed under "Known repository file locations" below (repo-root-relative, e.g. \
'backend/app.py'). If a mentioned file/symbol has no entry there, write "Unknown" for it instead \
of guessing or inventing a placeholder path such as '/path/to/allotmint/...'.

If the issue is already accurate and complete, return it unchanged.

Respond with exactly two parts, in this format and nothing else:
TITLE: <title>
BODY:
<body>

Original title: {title}

Original body:
{body}\
{file_hints_section}\
{feedback_section}
"""

FILE_HINTS_SECTION_TEMPLATE = """

Known repository file locations for names mentioned in this issue:
{hints}
"""

FEEDBACK_SECTION_TEMPLATE = """

The user reviewed a previous revision and gave this feedback -- incorporate it:
{feedback}
"""


def load_template_sections(template_path: Path = BUG_REPORT_TEMPLATE_PATH) -> list[str]:
    """Extract the ordered '## Section' headings from a GitHub issue template.

    Falls back to FALLBACK_TEMPLATE_SECTIONS if the template file is missing or empty,
    so a moved/renamed template degrades gracefully instead of breaking the tool.
    """
    try:
        text = template_path.read_text(encoding="utf-8")
    except OSError:
        return list(FALLBACK_TEMPLATE_SECTIONS)
    sections = re.findall(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    return sections or list(FALLBACK_TEMPLATE_SECTIONS)


def missing_sections(body: str, sections: list[str]) -> list[str]:
    """Return the required sections that have no '## <Section>' heading in body."""
    present = set(re.findall(r"^##\s+(.+?)\s*$", body, re.MULTILINE))
    return [section for section in sections if section not in present]


def fetch_issue(owner: str, repo: str, number: int) -> dict:
    """Fetch an issue's title/body/state via the `gh` CLI."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            str(number),
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "number,title,body,state,url",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        print(f"ERROR: Failed to fetch issue #{number}: {result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)

    import json

    return json.loads(result.stdout)


# Extensions searched for when an issue mentions a bare filename like 'foo.py'.
CODE_FILE_EXTENSIONS = ("tsx", "ts", "py", "jsx", "js", "css", "md", "yaml", "yml", "json")

# Symbol names (functions/classes) must be at least this many characters to be worth a
# repo-wide `git grep` -- short backticked tokens (`id`, `db`) are too noisy to search.
MIN_SYMBOL_LENGTH = 3


def list_repo_files(repo_root: Path) -> list[str]:
    """Return every git-tracked file path (relative to repo_root), or [] on any failure."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def find_repo_file_hints(text: str, repo_root: Path) -> dict[str, list[str]]:
    """Resolve filenames/symbols mentioned in issue text to real repo-relative paths.

    The model reviewing the issue has no filesystem access, so left to itself it
    invents plausible-looking but fake paths (e.g. '/path/to/allotmint/foo.py') for
    any file it's asked to cite. This grounds the prompt by searching the actual
    checkout for tracked files matching a bare filename, or containing a def/class
    matching a backticked symbol name, mentioned in the issue.
    """
    hints: dict[str, list[str]] = {}

    repo_files = list_repo_files(repo_root)
    files_by_basename: dict[str, list[str]] = {}
    for path in repo_files:
        files_by_basename.setdefault(Path(path).name, []).append(path)

    ext_pattern = "|".join(CODE_FILE_EXTENSIONS)
    for match in re.finditer(rf"\b([A-Za-z0-9_\-]+\.(?:{ext_pattern}))\b", text):
        filename = match.group(1)
        if filename in hints:
            continue
        matches = files_by_basename.get(filename)
        if matches:
            hints[filename] = matches

    for match in re.finditer(r"`([A-Za-z_][A-Za-z0-9_]*)`", text):
        symbol = match.group(1)
        if symbol in hints or len(symbol) < MIN_SYMBOL_LENGTH:
            continue
        result = subprocess.run(
            ["git", "grep", "-lI", "-E", rf"\b(def|class|function|const)\s+{re.escape(symbol)}\b"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        matches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if matches:
            hints[symbol] = matches

    return hints


def format_file_hints(hints: dict[str, list[str]]) -> str:
    """Render resolved file hints as a bullet list for the review prompt, or "" if empty."""
    if not hints:
        return ""
    lines = []
    for name, paths in hints.items():
        joined = ", ".join(f"`{path}`" for path in paths[:5])
        lines.append(f"- `{name}` -> {joined}")
    return FILE_HINTS_SECTION_TEMPLATE.format(hints="\n".join(lines))


def apply_known_file_paths(body: str, file_hints: dict[str, list[str]]) -> str:
    """Overwrite the '## Files Affected' section with paths resolved by find_repo_file_hints().

    Small local models are unreliable at copying exact paths back out of the prompt's hint
    block -- they tend to play it safe and write "Unknown" rather than risk echoing it wrong.
    Once we've resolved real paths ourselves, write them into the section directly instead of
    trusting the model to transcribe them.
    """
    if not file_hints:
        return body
    paths = sorted({path for matches in file_hints.values() for path in matches})
    if not paths:
        return body
    bullet_list = "\n".join(f"- `{path}`" for path in paths)
    pattern = re.compile(r"(^##\s+Files Affected\s*\n)(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
    if not pattern.search(body):
        return body
    return pattern.sub(lambda m: m.group(1) + bullet_list + "\n\n", body, count=1)


def build_review_prompt(
    title: str,
    body: str,
    feedback: str | None = None,
    file_hints: dict[str, list[str]] | None = None,
) -> str:
    """Build the prompt sent to the model to review and refresh the issue.

    When `feedback` is given (the user's response to a prior proposed revision),
    it's appended so the model can address it in the next attempt. `file_hints` are
    real repo-relative paths resolved by find_repo_file_hints() for filenames/symbols
    mentioned in the issue, so the model can cite accurate paths instead of guessing.
    """
    sections = ", ".join(f"'## {section}'" for section in load_template_sections())
    feedback_section = FEEDBACK_SECTION_TEMPLATE.format(feedback=feedback) if feedback else ""
    file_hints_section = format_file_hints(file_hints or {})
    return REVIEW_PROMPT_TEMPLATE.format(
        title=title,
        body=body,
        sections=sections,
        feedback_section=feedback_section,
        file_hints_section=file_hints_section,
    )


def run_review(
    model_source: str,
    title: str,
    body: str,
    verbose: bool = False,
    feedback: str | None = None,
    file_hints: dict[str, list[str]] | None = None,
) -> str | None:
    """Call the chosen model with the review prompt. Returns None on any failure."""
    prompt = build_review_prompt(title, body, feedback=feedback, file_hints=file_hints)

    if not validate_model_source(model_source):
        return None
    print(f"INFO: Reviewing with {describe_model_source(model_source)}...", file=sys.stderr)
    response = fetch_review(model_source, prompt)

    if verbose:
        print(f"[VERBOSE] Model response:\n{response}", file=sys.stderr)
    if not response.strip():
        print("ERROR: Model returned an empty response.", file=sys.stderr)
        return None
    return response


def looks_like_content_loss(original_body: str, revised_body: str) -> bool:
    """Return True when the revision is suspiciously shorter than the original.

    A model that garbles or drops sections of the issue tends to produce a much
    shorter body; this is a cheap guard, not a semantic check, so it only blocks
    approval and always leaves the final call to the user.
    """
    if not original_body.strip():
        return False
    return len(revised_body) < len(original_body) * MIN_BODY_LENGTH_RATIO


def print_diff(old_title: str, old_body: str, new_title: str, new_body: str) -> None:
    """Print a unified diff of the proposed title/body change."""
    old_lines = [f"Title: {old_title}\n", "\n", *[f"{line}\n" for line in old_body.splitlines()]]
    new_lines = [f"Title: {new_title}\n", "\n", *[f"{line}\n" for line in new_body.splitlines()]]
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="current", tofile="proposed")
    diff_text = "".join(diff)
    if not diff_text.strip():
        print("No changes proposed -- the issue already looks accurate.")
        return
    print()
    print("=" * 60)
    print("Proposed changes:")
    print("=" * 60)
    print(diff_text)
    print("=" * 60)


def update_issue(owner: str, repo: str, number: int, title: str, body: str, dry_run: bool) -> bool:
    """Update the issue's title/body on GitHub via `gh issue edit`. Returns success."""
    if dry_run:
        print(f"[DRY RUN] Would update issue #{number} with the title/body above.")
        return True

    body_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as tf:
            tf.write(body)
            body_path = tf.name

        result = subprocess.run(
            [
                "gh",
                "issue",
                "edit",
                str(number),
                "--repo",
                f"{owner}/{repo}",
                "--title",
                title,
                "--body-file",
                body_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    finally:
        if body_path and os.path.exists(body_path):
            os.unlink(body_path)

    if result.returncode != 0:
        print(f"ERROR: Failed to update issue #{number}: {result.stderr.strip()}", file=sys.stderr)
        return False
    print(f"[OK] Updated issue #{number}.")
    return True


def prompt_for_issue_number() -> int:
    """Interactively prompt for an issue number."""
    try:
        raw = input("Issue number to review: ").strip()
    except EOFError:
        raw = ""
    try:
        return int(raw)
    except ValueError:
        print(f"Invalid issue number: {raw!r}", file=sys.stderr)
        raise SystemExit(1) from None


def prompt_for_disposition() -> tuple[str, str | None]:
    """Ask the user to apply, reject, or send feedback on a proposed revision.

    Returns a ("apply" | "abort" | "retry", feedback) pair. Anything typed other than
    a y/n answer is treated as feedback for another review round.
    """
    try:
        raw = input(
            "Apply this update to the issue? [Y/n, or type feedback to have the model try "
            "again] "
        ).strip()
    except EOFError:
        return "abort", None
    lowered = raw.lower()
    if lowered in ("", "y", "yes"):
        return "apply", None
    if lowered in ("n", "no"):
        return "abort", None
    return "retry", raw


def main() -> int:
    """Run the interactive issue-review flow."""
    parser = argparse.ArgumentParser(
        description="Review and refresh a GitHub issue using a local or cloud LLM"
    )
    parser.add_argument("issue_id", type=int, nargs="?", help="GitHub issue number to review")
    parser.add_argument("--model", choices=[LOCAL, CLOUD], help="Model source (skips the prompt)")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt and update the issue if changes are proposed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the proposed diff and confirmation flow, but never call `gh issue edit`",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the raw model response",
    )
    args = parser.parse_args()

    try:
        owner, repo = get_repo_info()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    issue_id = args.issue_id if args.issue_id is not None else prompt_for_issue_number()
    model_source = args.model or prompt_for_model_source()

    print(f"INFO: Fetching issue #{issue_id} from {owner}/{repo}...", file=sys.stderr)
    issue = fetch_issue(owner, repo, issue_id)
    title = issue.get("title", "")
    body = issue.get("body") or ""
    if issue.get("state") == "CLOSED":
        print(f"WARNING: Issue #{issue_id} is closed.", file=sys.stderr)

    required_sections = load_template_sections()
    feedback: str | None = None

    try:
        repo_root = Path(get_repo_root())
        file_hints = find_repo_file_hints(f"{title}\n{body}", repo_root)
    except ValueError:
        file_hints = {}

    while True:
        response = run_review(
            model_source, title, body, args.verbose, feedback=feedback, file_hints=file_hints
        )
        if response is None:
            return 1

        new_title, new_body = parse_review_response(response, title, body)
        new_body = apply_known_file_paths(new_body, file_hints)

        if looks_like_content_loss(body, new_body):
            print(
                "ERROR: The revised body is far shorter than the original issue; refusing to "
                "propose a change that may have dropped details. Re-run with --verbose to "
                "inspect the raw model response.",
                file=sys.stderr,
            )
            return 1

        print_diff(title, body, new_title, new_body)

        missing = missing_sections(new_body, required_sections)
        if missing:
            print(
                f"WARNING: Proposed body is still missing required sections: {', '.join(missing)}",
                file=sys.stderr,
            )

        if new_title == title and new_body == body:
            return 0

        if args.yes:
            break

        action, feedback = prompt_for_disposition()
        if action == "apply":
            break
        if action == "abort":
            print("Aborted; issue left unchanged.", file=sys.stderr)
            return 0
        print("INFO: Re-reviewing with your feedback...", file=sys.stderr)

    return 0 if update_issue(owner, repo, issue_id, new_title, new_body, args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
