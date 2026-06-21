"""CLI tool to review a GitHub PR using local Ollama.

Takes a PR ID and calls Ollama to generate an advisory review, reusing the
shared review_common infrastructure. Requires gh CLI for fetching PR details.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Add parent directory to path to import review_common
sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".github" / "scripts"))
from ollama_common import (
    fetch_ollama_review,
    get_ollama_endpoint,
    get_ollama_model,
    validate_ollama_connection,
)
from review_common import build_prompt, emit_empty_diff_notice, finalize_review, truncate_diff


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
        # Handle both https and ssh URLs
        if url.startswith("git@"):
            # git@github.com:owner/repo.git
            match = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?$", url)
        else:
            # https://github.com/owner/repo.git
            match = re.search(r"github\.com/([^/]+)/(.+?)(?:\.git)?$", url)
        if match:
            return match.group(1), match.group(2).replace(".git", "")
    except FileNotFoundError as exc:
        raise ValueError(f"git command not found. Is git installed? {exc}") from exc
    except subprocess.CalledProcessError:
        pass
    raise ValueError("Could not determine GitHub repo from git remote origin")


def fetch_pr_details(owner: str, repo: str, pr_id: int) -> dict:
    """Fetch PR details using gh CLI."""
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pr_id),
                "--repo",
                f"{owner}/{repo}",
                "--json",
                "title,body,baseRefName",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except FileNotFoundError as exc:
        print(f"ERROR: gh CLI not found. Is GitHub CLI installed? {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Failed to fetch PR #{pr_id}: {exc.stderr}", file=sys.stderr)
        raise SystemExit(1) from exc


def fetch_pr_diff(owner: str, repo: str, pr_id: int) -> str:
    """Fetch the PR diff using gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", str(pr_id), "--repo", f"{owner}/{repo}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except FileNotFoundError as exc:
        print(f"ERROR: gh CLI not found. Is GitHub CLI installed? {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Failed to fetch diff for PR #{pr_id}: {exc.stderr}", file=sys.stderr)
        raise SystemExit(1) from exc


def extract_issue_body(pr_body: str, owner: str, repo: str) -> str:
    """Extract the linked issue body from PR description if present.

    PR body might contain references like 'Closes #1234'. We try to fetch
    the referenced issue if available. Uses the provided owner/repo.
    """
    if not pr_body:
        return "No linked issue found. Review code on its own merits."

    # Look for common issue reference patterns
    patterns = [r"Closes\s+#(\d+)", r"Fixes\s+#(\d+)", r"Resolves\s+#(\d+)"]
    for pattern in patterns:
        match = re.search(pattern, pr_body)
        if match:
            issue_id = match.group(1)
            try:
                result = subprocess.run(
                    [
                        "gh",
                        "issue",
                        "view",
                        issue_id,
                        "--repo",
                        f"{owner}/{repo}",
                        "--json",
                        "body",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                issue = json.loads(result.stdout)
                return issue.get("body", pr_body)
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

    return pr_body


def main() -> int:
    """Run the PR review flow."""
    parser = argparse.ArgumentParser(description="Review a GitHub PR using local Ollama")
    parser.add_argument("pr_id", type=int, help="GitHub PR ID to review")
    parser.add_argument(
        "--repo",
        help="GitHub repository (owner/repo format). Auto-detected from git remote if not provided.",  # noqa: E501
    )
    args = parser.parse_args()

    # Validate Ollama is reachable
    endpoint = get_ollama_endpoint()
    if not validate_ollama_connection(endpoint):
        print(
            f"ERROR: Ollama is not reachable at {endpoint}. "
            "Please start Ollama or set OLLAMA_ENDPOINT.",
            file=sys.stderr,
        )
        return 1

    model = get_ollama_model()

    # Get repo info
    try:
        if args.repo:
            parts = args.repo.split("/")
            if len(parts) != 2:
                print(f"ERROR: Invalid repo format '{args.repo}'. Use owner/repo.", file=sys.stderr)
                return 1
            owner, repo = parts
        else:
            owner, repo = get_repo_info()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"INFO: Reviewing PR #{args.pr_id} from {owner}/{repo}", file=sys.stderr)

    # Fetch PR details
    pr_details = fetch_pr_details(owner, repo, args.pr_id)
    pr_title = pr_details.get("title", "")
    pr_body = pr_details.get("body", "")
    issue_body = extract_issue_body(pr_body, owner, repo)

    # Fetch diff
    diff = fetch_pr_diff(owner, repo, args.pr_id)

    # Truncate diff if needed
    original_diff_len = len(diff)
    diff, was_truncated = truncate_diff(diff)
    if was_truncated:
        print(
            f"INFO: Truncated diff from {original_diff_len} to {len(diff)} characters",
            file=sys.stderr,
        )

    if not diff.strip():
        return emit_empty_diff_notice("Ollama")

    # Build prompt and fetch review
    prompt = build_prompt(pr_title, diff, issue_body, discussion="", verified_facts="")
    print(f"INFO: Using Ollama model '{model}'", file=sys.stderr)
    review = fetch_ollama_review(endpoint, model, prompt)

    return finalize_review(review, "ERROR: Ollama returned an empty review")


if __name__ == "__main__":
    raise SystemExit(main())
