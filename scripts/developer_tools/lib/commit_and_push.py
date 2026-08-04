"""CLI tool to commit local changes and push, using an LLM for the commit message.

Stages local changes, asks the chosen model (local Ollama or cloud DeepSeek,
via llm_common.py) to draft a commit message from the diff (falling back to a
plain default message when that model is unavailable or `--no-llm` is
passed), makes sure the message references the issue ID found in the current
branch name, commits, and pushes the branch to `origin`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from llm_common import (  # noqa: E402
    LOCAL,
    add_model_source_arg,
    describe_model_source,
    fetch_review,
    validate_model_source,
)
from publish_pr import extract_issue_id, get_current_branch, push_to_remote  # noqa: E402

MAIN_BRANCH = "main"


def refuse_if_main_branch(branch: str) -> None:
    """Exit with guidance if the current branch is the main branch."""
    if branch != MAIN_BRANCH:
        return
    print(
        f"ERROR: Refusing to commit directly to '{MAIN_BRANCH}'.\n"
        "Create or switch to a feature/bugfix branch first, e.g.:\n"
        "    git checkout -b fix/<issue-number>-short-description",
        file=sys.stderr,
    )
    raise SystemExit(1)


def get_git_root() -> str:
    """Get the root directory of the git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Not a git repository or git command failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def stage_changes(files: list[str] | None) -> None:
    """Stage the given files, or all changes (tracked and untracked) if none given."""
    try:
        if files:
            subprocess.run(["git", "add", "--", *files], check=True)
        else:
            subprocess.run(["git", "add", "-A"], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Failed to stage changes: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def has_staged_changes() -> bool:
    """Return True if there are staged changes ready to commit.

    `git diff --cached --quiet` exits 0 (no diff) or 1 (has diff); any other
    code means the command itself failed and must not be read as "changes".
    """
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    if result.returncode not in (0, 1):
        print(
            f"ERROR: 'git diff --cached --quiet' failed with exit code {result.returncode}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return result.returncode == 1


def get_staged_diff() -> str:
    """Return the diff of staged changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Failed to read staged changes: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    return result.stdout


MAX_DIFF_CHARS = 20_000


def build_commit_prompt(diff: str, issue_id: int | None) -> str:
    """Build the prompt used to draft a commit message from a diff."""
    issue_line = (
        f"Reference issue #{issue_id} in the message (e.g. a trailing 'Refs #{issue_id}' line)."
        if issue_id
        else "No issue is linked to this branch; do not invent an issue reference."
    )
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n... (diff truncated)"
    return f"""Write a git commit message for the following diff.

Rules:
- Subject line under 72 characters, imperative mood (e.g. "Fix", "Add", "Update").
- Optionally follow with a blank line and a short body explaining why, if useful.
- {issue_line}
- Output only the commit message, no preamble or code fences.

Diff:
{diff}
"""


def generate_commit_message(diff: str, issue_id: int | None, model_source: str) -> str | None:
    """Ask the chosen model to draft a commit message. Returns None on failure or empty diff."""
    if not diff.strip():
        return None
    prompt = build_commit_prompt(diff, issue_id)
    try:
        message = fetch_review(model_source, prompt)
    except SystemExit:
        return None
    return message.strip() or None


def ensure_issue_reference(message: str, issue_id: int | None) -> str:
    """Append a 'Refs #<issue_id>' trailer if the message doesn't already mention it."""
    if issue_id is None:
        return message
    marker = f"#{issue_id}"
    if marker in message:
        return message
    return f"{message}\n\nRefs {marker}"


def commit_changes(message: str) -> bool:
    """Commit staged changes with the given message."""
    try:
        subprocess.run(["git", "commit", "-m", message], check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Failed to commit: {exc}", file=sys.stderr)
        return False


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Commit local changes (with an LLM-drafted message) and push to origin"
    )
    parser.add_argument(
        "--message",
        "-m",
        default=None,
        help="Commit message override (skips LLM generation)",
    )
    parser.add_argument(
        "--files",
        "-f",
        nargs="+",
        default=None,
        help="Specific files to stage (default: all changed files)",
    )
    parser.add_argument(
        "--no-llm",
        "--no-ollama",
        dest="no_llm",
        action="store_true",
        help="Skip the LLM and use a plain default commit message",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Ollama model name, only used when --model-source=local "
            "(default: OLLAMA_MODEL env var or 'qwen2.5-coder:7b'). "
            "--model-source is not required alongside --model: it already "
            "defaults to 'local' (see add_model_source_arg), which is the "
            "only source --model applies to. Passing --model with an "
            "explicit --model-source cloud is accepted but ignored with a "
            "warning below, rather than rejected, so cloud runs stay usable "
            "without having to drop a leftover --model flag."
        ),
    )
    add_model_source_arg(parser)
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Commit only; skip pushing the branch to origin",
    )
    return parser


def main() -> int:
    """Stage, commit, and optionally push changes based on CLI arguments."""
    args = build_arg_parser().parse_args()

    if args.model and args.model_source == LOCAL:
        os.environ["OLLAMA_MODEL"] = args.model

    # Add warning for --model with --model-source cloud
    if args.model and args.model_source != LOCAL:
        print(
            "Warning: --model is only supported with --model-source local; "
            "ignoring --model for cloud model source.",
            file=sys.stderr,
        )

    os.chdir(get_git_root())

    branch = get_current_branch()
    refuse_if_main_branch(branch)
    issue_id = extract_issue_id(branch)

    stage_changes(args.files)

    if not has_staged_changes():
        print("No staged changes to commit.", file=sys.stderr)
        return 0

    message = args.message
    if not message and not args.no_llm:
        if validate_model_source(args.model_source):
            print(
                f"INFO: Generating commit message with "
                f"{describe_model_source(args.model_source)}...",
                file=sys.stderr,
            )
            diff = get_staged_diff()
            message = generate_commit_message(diff, issue_id, args.model_source)
        else:
            print("WARNING: Model unavailable. Using a default message.", file=sys.stderr)

    if not message:
        message = f"Work on issue #{issue_id}" if issue_id else "Commit local changes"

    message = ensure_issue_reference(message, issue_id)

    if not commit_changes(message):
        return 1
    print(f"Committed: {message.splitlines()[0]}")

    if args.no_push:
        return 0

    if not push_to_remote(branch):
        return 1
    print(f"Pushed branch '{branch}' to origin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
