"""Interactive CLI to create a well-structured GitHub issue from the command line.

Prompts for each section of the standard issue template with sensible defaults,
then creates the issue via the GitHub API (with a ``gh`` CLI fallback).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import requests

GITHUB_API_BASE = "https://api.github.com"

TEMPLATE_FEATURE = "feature"
TEMPLATE_BUG = "bug"

SECTIONS_FEATURE = [
    ("What", "What should be built or changed?"),
    ("Why", "Why is this needed? What problem does it solve, or what value does it add?"),
    ("How", "Outline the intended approach at a high level."),
    (
        "Constraints",
        (
            "Anything the implementation must respect"
            " (e.g. backwards compatibility, scope boundaries)."
        ),
    ),
    ("LLM tier", "Suggested AI agent tier: haiku / sonnet / opus"),
    (
        "Success looks like",
        "Checklist of acceptance criteria. Start each line with '- [ ] '.",
    ),
    (
        "Failure looks like",
        "What regressions or gaps would mean this failed. Start each line with '-'.",
    ),
]

SECTIONS_BUG = [
    ("What", "What is broken? Describe the observed behavior."),
    ("Why", "Why does this matter? What's the user/dev impact?"),
    ("How", "Steps to reproduce, and (if known) what the fix likely involves."),
    ("Constraints", "Anything the fix must not break."),
    ("LLM tier", "Suggested AI agent tier: haiku / sonnet / opus"),
    (
        "Success looks like",
        "Checklist of acceptance criteria. Start each line with '- [ ] '.",
    ),
    (
        "Failure looks like",
        "What regressions or gaps would mean the fix failed. Start each line with '-'.",
    ),
]


def get_repo_info() -> tuple[str, str]:
    """Extract owner and repo from git remote origin."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
        if url.startswith("git@"):
            match = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?$", url)
        else:
            match = re.search(r"github\.com/([^/]+)/(.+?)(?:\.git)?$", url)
        if match:
            repo = match.group(2)
            if repo.endswith(".git"):
                repo = repo[:-4]
            return match.group(1), repo
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Could not determine GitHub repo from git remote origin: {exc}") from exc
    raise ValueError("Could not determine GitHub repo from git remote origin")


def get_github_token() -> str:
    """Get GitHub token from GITHUB_TOKEN env var or ``gh auth token``."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print("Error: GITHUB_TOKEN env var not set and 'gh auth token' failed.", file=sys.stderr)
    sys.exit(1)


def prompt(label: str, hint: str, default: str = "") -> str:
    """Prompt the user for a multi-line value.

    Print the label and hint, then read lines until an empty line is entered
    (or just Enter for single-line-default behaviour when no default is given
    and this is the first / only line).
    """
    print()
    print(f"── {label} ──")
    print(f"   {hint}")
    if default:
        print(f"   Default: {default}")
    print("   (Enter your text. A single '.' on its own line finishes input.)")
    print()

    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == ".":
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    if not text and default:
        return default
    return text


def prompt_single(
    label: str, hint: str, default: str = "", options: list[str] | None = None
) -> str:
    """Prompt the user for a single-line value."""
    opts_hint = ""
    if options:
        opts_hint = f" [{'/'.join(options)}]"
    print()
    print(f"── {label}{opts_hint} ──")
    print(f"   {hint}")
    if default:
        print(f"   Default: {default}")
    try:
        value = input("> ").strip()
    except EOFError:
        value = ""
    if not value and default:
        return default
    return value


def pick_issue_type() -> str:
    """Let the user choose between a feature request and a bug report."""
    print()
    print("Issue type:")
    print("  [f] Feature request")
    print("  [b] Bug report")
    try:
        choice = input("> ").strip().lower()
    except EOFError:
        choice = "f"
    if choice in ("b", "bug"):
        return TEMPLATE_BUG
    return TEMPLATE_FEATURE


def format_feature_body(sections: dict[str, str]) -> str:
    """Format a feature-request body from the collected sections."""
    parts = [
        "## What",
        "",
        sections.get("What", ""),
        "",
        "## Why",
        "",
        sections.get("Why", ""),
        "",
        "## How",
        "",
        sections.get("How", ""),
        "",
        "## Constraints",
        "",
        sections.get("Constraints", "None"),
        "",
        "## LLM tier",
        "",
        sections.get("LLM tier", "sonnet"),
        "",
        "## Success looks like",
        "",
        sections.get("Success looks like", "- [ ] "),
        "",
        "## Failure looks like",
        "",
        sections.get("Failure looks like", "-"),
    ]
    return "\n".join(parts)


def format_bug_body(sections: dict[str, str]) -> str:
    """Format a bug-report body from the collected sections."""
    parts = [
        "## What",
        "",
        sections.get("What", ""),
        "",
        "## Why",
        "",
        sections.get("Why", ""),
        "",
        "## How",
        "",
        sections.get("How", ""),
        "",
        "## Constraints",
        "",
        sections.get("Constraints", "None"),
        "",
        "## LLM tier",
        "",
        sections.get("LLM tier", "sonnet"),
        "",
        "## Success looks like",
        "",
        sections.get("Success looks like", "- [ ] "),
        "",
        "## Failure looks like",
        "",
        sections.get("Failure looks like", "-"),
    ]
    return "\n".join(parts)


def create_issue_via_api(
    owner: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    token: str,
) -> str | None:
    """Create a GitHub issue via the REST API.  Returns the HTML URL on success."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("html_url")
    except requests.RequestException as exc:
        print(f"API request failed: {exc}", file=sys.stderr)
        return None


def create_issue_via_gh(
    owner: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
) -> str | None:
    """Create a GitHub issue via the ``gh`` CLI.  Returns the URL on success."""
    # Write body to a temp file so the CLI can read it safely on all platforms.
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            encoding="utf-8",
            delete=False,
        ) as tf:
            tf.write(body)
            body_path = tf.name

        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            f"{owner}/{repo}",
            "--title",
            title,
            "--body-file",
            body_path,
        ]
        for label in labels:
            cmd.extend(["--label", label])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        os.unlink(body_path)

        if result.returncode != 0:
            print(f"gh CLI failed: {result.stderr.strip()}", file=sys.stderr)
            return None

        url = result.stdout.strip()
        return url if url else None
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"gh CLI error: {exc}", file=sys.stderr)
        return None


def derive_title_from_what(what: str) -> str | None:
    """Extract a candidate title from the first meaningful line of 'What'."""
    if not what:
        return None
    lines = [line.strip() for line in what.splitlines() if line.strip()]
    if not lines:
        return None
    first = lines[0]
    # Cap at a reasonable title length
    if len(first) > 120:
        first = first[:117] + "..."
    return first


def confirm_and_create(
    owner: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    token: str,
) -> None:
    """Show a preview and ask for confirmation, then create the issue."""
    print()
    print("=" * 60)
    print(f"Repository: {owner}/{repo}")
    print(f"Title:      {title}")
    print(f"Labels:     {', '.join(labels) if labels else '(none)'}")
    print("=" * 60)
    print()
    print(body)
    print()
    print("=" * 60)

    try:
        confirm = input("Create this issue? [Y/n] ").strip().lower()
    except EOFError:
        confirm = "y"

    if confirm and confirm not in ("y", "yes", ""):
        print("Aborted.", file=sys.stderr)
        sys.exit(0)

    print()
    print("Creating issue via API...")
    url = create_issue_via_api(owner, repo, title, body, labels, token)

    if not url:
        print("Falling back to gh CLI...")
        url = create_issue_via_gh(owner, repo, title, body, labels)

    if url:
        # Extract issue number from URL for a concise summary
        match = re.search(r"/issues/(\d+)", url)
        if match:
            print(f"\n[OK] Created issue #{match.group(1)}: {url}")
        else:
            print(f"\n[OK] Created issue: {url}")
    else:
        print("Failed to create issue.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Run the interactive issue-creation workflow."""
    print("GitHub Issue Creator")
    print("=" * 60)

    # Resolve repo info
    try:
        owner, repo = get_repo_info()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Target repository: {owner}/{repo}")

    # Get token early so we fail fast if auth is missing
    token = get_github_token()

    # Pick issue type → determines template and default label
    issue_type = pick_issue_type()
    sections_def = SECTIONS_FEATURE if issue_type == TEMPLATE_FEATURE else SECTIONS_BUG
    default_label = "enhancement" if issue_type == TEMPLATE_FEATURE else "bug"

    # Collect sections
    sections: dict[str, str] = {}
    for label, hint in sections_def:
        default = ""
        if label == "LLM tier":
            default = "sonnet"
        elif label == "Success looks like":
            default = "- [ ] "
        elif label == "Failure looks like":
            default = "-"
        elif label == "Constraints":
            default = "None"

        value = prompt(label, hint, default=default)
        sections[label] = value

    # Derive or prompt for title
    derived_title = derive_title_from_what(sections.get("What", ""))
    title = prompt_single(
        "Title",
        "Issue title (short and descriptive).",
        default=derived_title or "",
    )
    if not title:
        print("Error: Title is required.", file=sys.stderr)
        sys.exit(1)

    # Prompt for labels
    labels_input = prompt_single(
        "Labels",
        "Comma-separated label names.",
        default=default_label,
    )
    labels = [lbl.strip() for lbl in labels_input.split(",") if lbl.strip()]

    # Assemble body
    if issue_type == TEMPLATE_BUG:
        body = format_bug_body(sections)
    else:
        body = format_feature_body(sections)

    # Confirm and create
    confirm_and_create(owner, repo, title, body, labels, token)


if __name__ == "__main__":
    main()
