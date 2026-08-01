"""CLI tool to extract GitHub issue prompts for Aider with local LLM assistance."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from lib.github_repo import get_repo_info
from lib.ollama_common import (
    fetch_ollama_review,
    get_ollama_endpoint,
    get_ollama_model,
    validate_ollama_connection,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract GitHub issue prompt for Aider with local LLM assistance",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-i",
        "--issue",
        type=int,
        dest="issue_id",
        help="GitHub issue ID (fetches from GitHub)",
    )
    group.add_argument(
        "-f",
        "--file",
        type=str,
        dest="issue_file",
        help="Local markdown file containing issue",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose/debug output",
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation and proceed directly to Aider",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="GitHub personal access token (optional, uses GITHUB_TOKEN env var if not provided)",
    )

    return parser.parse_args(argv)


def fetch_issue_from_github(
    owner: str,
    repo: str,
    issue_id: int,
    token: str | None = None,
    verbose: bool = False,
) -> tuple[str, str]:
    """Fetch issue title and body from GitHub API.

    Returns: (title, body) tuple.
    """
    if verbose:
        print(f"[DEBUG] Fetching issue #{issue_id} from {owner}/{repo}...", file=sys.stderr)

    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_id}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"ERROR: Failed to fetch issue #{issue_id}: {exc}", file=sys.stderr)
        print(
            "Tip: If GitHub API is unreachable, use -f <file> to load a local "
            "markdown file instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    issue = resp.json()
    title = issue.get("title", "")
    body = issue.get("body", "")

    if not title:
        print(f"ERROR: Issue #{issue_id} has no title", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"[DEBUG] Fetched issue: {title}", file=sys.stderr)

    return title, body


def load_issue_from_file(file_path: str, verbose: bool = False) -> tuple[str, str]:
    """Load issue title and body from a local markdown file.

    File format: first line is title, rest is body.
    Returns: (title, body) tuple.
    """
    if verbose:
        print(f"[DEBUG] Loading issue from file: {file_path}", file=sys.stderr)

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"ERROR: Failed to read file {file_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    lines = content.strip().split("\n", 1)
    title = lines[0].strip()
    body = lines[1].strip() if len(lines) > 1 else ""

    if verbose:
        print(f"[DEBUG] Loaded issue: {title}", file=sys.stderr)

    return title, body


def parse_issue_body(body: str, verbose: bool = False) -> dict[str, str]:
    """Parse issue body into structured sections.

    Extracts: What, Why, How, Constraints, LLM tier, Success looks like, Failure looks like.
    """
    sections = {}

    # Split by markdown headers (## Section)
    pattern = r"##\s*([^\n]+)\n(.*?)(?=##\s*|\Z)"
    matches = re.finditer(pattern, body, re.DOTALL | re.IGNORECASE)

    for match in matches:
        section_title = match.group(1).strip().lower()
        section_content = match.group(2).strip()

        # Normalize section names
        if section_title in ("what", "description"):
            sections["what"] = section_content
        elif section_title == "why":
            sections["why"] = section_content
        elif section_title == "how":
            sections["how"] = section_content
        elif section_title == "constraints":
            sections["constraints"] = section_content
        elif section_title in ("llm tier", "llm_tier"):
            sections["llm_tier"] = section_content
        elif section_title in ("success looks like", "success_looks_like"):
            sections["success"] = section_content
        elif section_title in ("failure looks like", "failure_looks_like"):
            sections["failure"] = section_content

    if verbose:
        print(f"[DEBUG] Parsed sections: {list(sections.keys())}", file=sys.stderr)

    return sections


def is_safe_relative_path(path: str) -> bool:
    """Reject absolute paths and paths that escape the repo root via '..' segments.

    Issue bodies and Ollama's suggestions are both untrusted input; without
    this check a path like '../../.aws/credentials' could be handed straight
    to aider if such a file happens to exist relative to the cwd.

    Path.is_absolute() alone isn't enough here: PureWindowsPath treats a
    leading '/' with no drive letter (e.g. '/etc/passwd') as relative, so a
    script running on Windows would miss it. Reject a leading separator of
    either style explicitly before falling back to is_absolute() for
    drive-letter and POSIX-root paths.
    """
    if path.startswith(("/", "\\")):
        return False
    candidate = Path(path)
    if candidate.is_absolute():
        return False
    return ".." not in candidate.parts


def extract_file_paths_from_issue(
    issue_body: str,
    verbose: bool = False,
) -> list[str]:
    """Extract file paths mentioned in the issue body.

    Looks for paths that exist in the repo (basic heuristic).
    """
    paths = []

    # Match common path patterns: src/foo.ts, backend/app.py, etc.
    pattern = r"(?:^|\s)([a-zA-Z0-9._/\-]+\.(?:ts|tsx|py|js|jsx|css|md|yml|yaml|json))"
    matches = re.finditer(pattern, issue_body, re.MULTILINE)

    for match in matches:
        path = match.group(1)
        if not is_safe_relative_path(path):
            continue
        if Path(path).exists():
            paths.append(path)
            if verbose:
                print(f"[DEBUG] Found file reference: {path}", file=sys.stderr)

    return list(set(paths))  # deduplicate


def suggest_files_with_ollama(
    issue_title: str,
    issue_body: str,
    extracted_paths: list[str],
    endpoint: str,
    model: str,
    verbose: bool = False,
) -> list[str]:
    """Use Ollama to suggest which files to add to Aider based on the issue.

    Returns: list of suggested file paths.
    """
    if verbose:
        print(f"[DEBUG] Calling Ollama ({model}) to suggest files...", file=sys.stderr)

    extracted_summary = ", ".join(extracted_paths) if extracted_paths else "none"
    prompt = f"""You are a code analysis assistant. Based on the GitHub issue below, identify
which files should be reviewed or modified to implement the requested change.

Issue Title: {issue_title}

Issue Description:
{issue_body}

Extracted file references from issue: {extracted_summary}

Return ONLY a JSON array of file paths to include, like:
["src/components/Foo.tsx", "backend/app.py"]

Do not include test files or lock files. Be concise."""

    try:
        response = fetch_ollama_review(endpoint, model, prompt)
    except SystemExit:
        # Ollama failed; return what we extracted
        if verbose:
            print(
                "[DEBUG] Ollama query failed; using extracted paths only",
                file=sys.stderr,
            )
        return extracted_paths

    # Parse JSON response
    try:
        # Find JSON array in response
        start = response.find("[")
        end = response.rfind("]")
        if start != -1 and end != -1:
            json_str = response[start : end + 1]
            suggested = json.loads(json_str)
            if isinstance(suggested, list):
                # Filter to existing, safe (non-traversal) files
                existing = [
                    p
                    for p in suggested
                    if isinstance(p, str) and is_safe_relative_path(p) and Path(p).exists()
                ]
                if verbose:
                    print(
                        f"[DEBUG] Ollama suggested {len(existing)} files: {existing}",
                        file=sys.stderr,
                    )
                return existing
    except (json.JSONDecodeError, ValueError):
        pass

    if verbose:
        print(
            "[DEBUG] Could not parse Ollama response as JSON; using extracted paths",
            file=sys.stderr,
        )
    return extracted_paths


def resolve_files_to_edit(
    title: str,
    body: str,
    endpoint: str,
    model: str,
    verbose: bool = False,
) -> list[str]:
    """Return the files to hand to aider.

    Prefers file paths already mentioned in the issue body; falls back to
    asking Ollama to suggest files only when none are found there.
    """
    extracted_paths = extract_file_paths_from_issue(body, verbose)
    if extracted_paths:
        if verbose:
            print(f"[DEBUG] Using extracted paths: {extracted_paths}", file=sys.stderr)
        return extracted_paths

    if verbose:
        print(
            "[DEBUG] No files extracted from issue; asking Ollama to suggest...",
            file=sys.stderr,
        )
    return suggest_files_with_ollama(title, body, extracted_paths, endpoint, model, verbose)


def formulate_aider_prompt(
    issue_title: str,
    parsed_sections: dict[str, str],
    verbose: bool = False,
) -> str:
    """Formulate the prompt to pass to Aider based on parsed issue sections."""
    prompt_lines = [issue_title]

    if verbose:
        print("[DEBUG] Formulating Aider prompt...", file=sys.stderr)

    # Add structured sections
    for section in ["what", "why", "how", "constraints", "success", "failure"]:
        if section in parsed_sections:
            content = parsed_sections[section].strip()
            if content:
                section_title = section.replace("_", " ").title()
                prompt_lines.append(f"\n{section_title}:\n{content}")

    prompt = "\n".join(prompt_lines)

    if verbose:
        print(f"[DEBUG] Prompt length: {len(prompt)} characters", file=sys.stderr)

    return prompt


def confirm_with_user(
    files: list[str],
    prompt: str,
    no_confirm: bool = False,
    verbose: bool = False,
) -> bool:
    """Show files and prompt to user for confirmation."""
    print("\n" + "=" * 70)
    print("AIDER EXTRACTION SUMMARY")
    print("=" * 70)

    print(f"\nFiles to add to Aider ({len(files)}):")
    for f in files:
        print(f"  - {f}")

    print("\nPrompt for Aider:")
    print("-" * 70)
    print(prompt)
    print("-" * 70)

    if no_confirm:
        if verbose:
            print("[DEBUG] --no-confirm flag set; skipping confirmation", file=sys.stderr)
        return True

    print("\nProceed with Aider? (y/n): ", end="", flush=True)
    try:
        response = input().strip().lower()
        return response in ("y", "yes")
    except EOFError:
        print("(EOF received; skipping confirmation)", file=sys.stderr)
        return False


def _run_aider(cmd: list[str]) -> subprocess.CompletedProcess[bytes]:
    """Run one aider invocation with inherited stdio, translating aider-not-found
    and Ctrl+C into the same clean-exit handling both call sites need."""
    try:
        return subprocess.run(cmd, check=False)
    except FileNotFoundError:
        print("ERROR: aider not found. Install it with: pip install aider-chat", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[OK] Aider session interrupted by user", file=sys.stderr)
        sys.exit(0)


def run_aider(files: list[str], prompt: str, verbose: bool = False) -> None:
    """Apply the initial prompt, then hand off to an interactive aider session.

    Aider's --message/--message-file explicitly disable chat mode: they send
    one message, apply the reply, and exit -- they cannot themselves stay
    interactive afterward. So the initial prompt is applied non-interactively
    first, then aider is launched again with no message and inherited stdio,
    giving the user a real interactive REPL as the issue's AC requires.
    Aider's own .aider.chat.history.md carries the conversation across both
    invocations.
    """
    if not files:
        print("ERROR: No files to add to Aider; aborting.", file=sys.stderr)
        sys.exit(1)

    message_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    try:
        message_file.write(prompt)
        message_file.close()
        if verbose:
            print(f"[DEBUG] Applying initial prompt to {len(files)} files...", file=sys.stderr)
        initial = _run_aider(["aider", "--message-file", message_file.name, *files])
    finally:
        Path(message_file.name).unlink(missing_ok=True)

    if initial.returncode != 0:
        print(
            f"ERROR: aider exited with status {initial.returncode} "
            "while applying the initial prompt",
            file=sys.stderr,
        )
        sys.exit(initial.returncode)

    if verbose:
        print("[DEBUG] Handing off to an interactive aider session...", file=sys.stderr)
    interactive = _run_aider(["aider", *files])
    if interactive.returncode != 0:
        print(f"ERROR: aider exited with status {interactive.returncode}", file=sys.stderr)
        sys.exit(interactive.returncode)


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    args = parse_args(argv)

    # Fail early if Ollama isn't running, before any GitHub/file I/O -- per
    # the issue's constraint, nothing else here is useful without it.
    endpoint = get_ollama_endpoint()
    model = get_ollama_model()

    if args.verbose:
        print(f"[DEBUG] Ollama endpoint: {endpoint}", file=sys.stderr)
        print(f"[DEBUG] Ollama model: {model}", file=sys.stderr)

    if not validate_ollama_connection(endpoint):
        print("ERROR: Ollama serve must be running", file=sys.stderr)
        print(f"ERROR: Could not connect to {endpoint}", file=sys.stderr)
        sys.exit(1)

    # Get repo info (for GitHub fetching)
    if args.issue_id:
        try:
            owner, repo = get_repo_info()
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

    # Fetch or load issue
    if args.issue_id:
        token = args.token or os.getenv("GITHUB_TOKEN")
        title, body = fetch_issue_from_github(owner, repo, args.issue_id, token, args.verbose)
    else:
        title, body = load_issue_from_file(args.issue_file, args.verbose)

    # Parse issue structure
    parsed = parse_issue_body(body, args.verbose)

    files = resolve_files_to_edit(title, body, endpoint, model, args.verbose)
    if not files:
        print(
            "WARNING: No files found or suggested. Proceeding with empty file list.",
            file=sys.stderr,
        )

    # Formulate prompt
    prompt = formulate_aider_prompt(title, parsed, args.verbose)

    # Confirm with user
    if not confirm_with_user(files, prompt, args.no_confirm, args.verbose):
        print("[OK] Aborted by user")
        sys.exit(0)

    # Run Aider
    run_aider(files, prompt, args.verbose)

    print("[OK] Aider session complete")


if __name__ == "__main__":
    main()
