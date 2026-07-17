"""CLI tool to publish a PR from the current branch with optional Ollama assistance."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests


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
    except subprocess.CalledProcessError:
        pass
    raise ValueError("Could not determine GitHub repo from git remote origin")


def get_current_branch() -> str:
    """Get the current branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"Failed to get current branch: {exc}", file=sys.stderr)
        sys.exit(1)


def extract_issue_id(branch_name: str) -> Optional[int]:
    """Extract issue ID from branch name (e.g., 'fix/issue-4445-slug' -> 4445)."""
    match = re.search(r"issue-(\d+)", branch_name)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)", branch_name)
    if match:
        return int(match.group(1))
    return None


def get_default_branch(owner: str, repo: str) -> str:
    """Get the default branch name."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", f"{owner}/{repo}", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or "main"
    except subprocess.CalledProcessError:
        pass
    return "main"


def check_working_tree_clean() -> bool:
    """Check if working tree has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        return not result.stdout.strip()
    except subprocess.CalledProcessError:
        return False


def get_changed_files(branch: str, default_branch: str = "main") -> list[str]:
    """Get list of changed files: either uncommitted changes or commits on the branch."""
    changed_files = []
    remote_default_branch = f"origin/{default_branch or 'main'}"
    try:
        # Check for both staged and unstaged changes
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            uncommitted_changes = result.stdout.strip().split("\n")
            changed_files.extend(uncommitted_changes)

        # Check for commits on the branch only if we have a merge base
        result = subprocess.run(
            ["git", "merge-base", branch, remote_default_branch],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            merge_base = result.stdout.strip()
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{merge_base}...HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                committed_changes = result.stdout.strip().split("\n")
                changed_files.extend(committed_changes)

    except subprocess.CalledProcessError:
        pass

    # remove duplicates
    return list(set(changed_files))


def stage_and_commit(
    files: Optional[list[str]], message: str, branch: str, default_branch: str = "main"
) -> bool:
    """Stage and commit the specified files (or changed files in branch if none specified)."""
    try:
        if not files:
            # Auto-detect changed files in the branch
            files = get_changed_files(branch, default_branch)
            if not files:
                print("No changed files found in branch. Nothing to commit.", file=sys.stderr)
                return False

        # Stage specified files
        for f in files:
            subprocess.run(["git", "add", f], check=True)

        subprocess.run(["git", "commit", "-m", message], check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"Failed to commit: {exc}", file=sys.stderr)
        return False


def branch_is_ahead_of_main(branch: str, default_branch: str) -> bool:
    """Check if branch has commits ahead of the default branch."""
    try:
        # First check if default_branch is an ancestor of branch
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", default_branch, branch],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return False

        # Then verify branch actually has commits NOT in default_branch
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{default_branch}..{branch}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            commit_count = int(result.stdout.strip())
            return commit_count > 0
        return False
    except (subprocess.CalledProcessError, ValueError):
        return False


def push_to_remote(branch: str) -> bool:
    """Push the branch to remote."""
    try:
        subprocess.run(["git", "push", "-u", "origin", branch], check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"Failed to push: {exc}", file=sys.stderr)
        return False


def fetch_issue(owner: str, repo: str, issue_id: int) -> Optional[dict]:
    """Fetch issue details from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        print(f"Failed to fetch issue #{issue_id}: {exc}", file=sys.stderr)
        return None

def get_ollama_server_url(host: str = "localhost", port: int = 11434) -> str:
    """Get Ollama server url."""
    return f"http://{host}:{port}"

def is_ollama_running(host: str = "localhost", port: int = 11434) -> bool:
    """Check if Ollama is running locally."""
    try:
        host_url= get_ollama_server_url(host=host, port=port)
        resp = requests.get(f"{host_url}/api/tags", timeout=2)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def get_ollama_model() -> str:
    """Get Ollama model name from env, available models, or default."""
    # Check if explicitly set in env
    model = os.getenv("OLLAMA_MODEL")
    if model:
        return model

    # Try to get available models from Ollama
    try:
        ollama_url = get_ollama_server_url()
        resp = requests.get(f"{ollama_url}/api/tags", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("models", [])
            if models:
                # Prefer coder models, otherwise use first available
                for model in models:
                    name = model.get("name", "")
                    if "coder" in name.lower():
                        return name
                return models[0].get("name", "mistral")
    except requests.RequestException:
        pass

    return "mistral"


def generate_pr_body_with_ollama(issue_title: str, issue_body: str, model: str) -> Optional[str]:
    """Use Ollama to generate PR body sections."""
    prompt = f"""Given this GitHub issue, generate a concise PR description with the following sections:

## What
Brief explanation of what was changed or implemented.

## Why
Why this change matters and what problem it solves.

## Testing
How the changes were tested.

## Checklist
- [ ] Tests added/updated
- [ ] Docs updated if needed
- [ ] No breaking changes

Issue title: {issue_title}

Issue body:
{issue_body}

Generate only the sections above, no preamble."""

    ollama_url = get_ollama_server_url()
    try:
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.7,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", "").strip()
    except requests.RequestException as exc:
        print(f"Ollama generation failed: {exc}", file=sys.stderr)
    return None


def create_placeholder_pr_body(issue_id: int, issue_title: str, issue_body: str) -> str:
    """Create a placeholder PR body when Ollama is not available."""
    return f"""## What
<!-- Describe what changed -->

## Why
{issue_body[:200] if issue_body else "<!-- Explain why this change matters -->"}

## Testing
<!-- How was this tested? -->

## Checklist
- [ ] Tests added/updated
- [ ] Docs updated if needed
- [ ] No breaking changes

Closes #{issue_id}"""


def create_pr(
    owner: str,
    repo: str,
    branch: str,
    default_branch: str,
    title: str,
    body: str,
) -> Optional[str]:
    """Create a PR and return the URL."""
    body_file = None
    try:
        # Write body to temp file to avoid command-line quoting issues
        body_file = Path.home() / f".pr-body-{os.getpid()}.txt"
        body_file.write_text(body, encoding="utf-8")

        result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body-file",
                str(body_file),
                "--head",
                branch,
                "--base",
                default_branch,
                "--repo",
                f"{owner}/{repo}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            match = re.search(r"https://github\.com/[^\s]+/pull/\d+", result.stdout)
            if match:
                return match.group(0)
            return result.stdout.strip()
        else:
            print(f"Failed to create PR: {result.stderr}", file=sys.stderr)
            return None
    except Exception as exc:
        print(f"Error creating PR: {exc}", file=sys.stderr)
        return None
    finally:
        if body_file:
            body_file.unlink(missing_ok=True)


def check_gh_available() -> None:
    """Verify gh CLI is installed and authenticated, exiting with a clear message if not."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print(
            "Error: GitHub CLI (gh) is not installed. "
            "Install from https://cli.github.com/",
            file=sys.stderr,
        )
        sys.exit(1)

    if result.returncode != 0:
        print(
            "Error: GitHub CLI (gh) is not authenticated. "
            "Run 'gh auth login'.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a PR from the current branch")
    parser.add_argument(
        "--message",
        "-m",
        default=None,
        help="Commit message (default: 'Work on issue #NNNN')",
    )
    parser.add_argument(
        "--files",
        "-f",
        nargs="+",
        default=None,
        help="Specific files to commit (default: all changed files)",
    )
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        help="Skip Ollama and use placeholder PR body",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama model name (default: OLLAMA_MODEL env var or 'mistral')",
    )
    args = parser.parse_args()

    # Change to git root directory
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        git_root = result.stdout.strip()
        os.chdir(git_root)
    except subprocess.CalledProcessError:
        print("Error: Could not determine git root directory", file=sys.stderr)
        sys.exit(1)

    # Get repo info
    try:
        owner, repo = get_repo_info()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Using repository: {owner}/{repo}")

    # Get current branch
    branch = get_current_branch()
    print(f"Current branch: {branch}")

    # Extract issue ID
    issue_id = extract_issue_id(branch)
    if not issue_id:
        print(f"Error: Could not extract issue ID from branch name '{branch}'", file=sys.stderr)
        print("Branch name should match pattern: fix/issue-NNNN-* or feat/issue-NNNN-*", file=sys.stderr)
        sys.exit(1)

    print(f"Issue ID: #{issue_id}")

    # Fetch issue
    print(f"Fetching issue #{issue_id}...")
    issue = fetch_issue(owner, repo, issue_id)
    if not issue:
        sys.exit(1)

    issue_title = issue.get("title", "")
    issue_body = issue.get("body", "")
    print(f"Issue title: {issue_title}")

    # Get default branch
    default_branch = get_default_branch(owner, repo)
    print(f"Target branch: {default_branch}")

    # Check if branch is ahead of main
    if not branch_is_ahead_of_main(branch=branch, default_branch=default_branch):
        print(f"Error: Branch '{branch}' is not ahead of '{default_branch}'", file=sys.stderr)
        sys.exit(1)

    # Stage and commit
    print("Staging and committing changes...")
    if check_working_tree_clean():
        print("Working tree is already clean. No new changes to commit.")
    else:
        commit_msg = args.message or f"Work on issue #{issue_id}"
        if stage_and_commit(args.files, commit_msg, branch, default_branch):
            print(f"Committed: {commit_msg}")
        else:
            print("No changes to commit, but continuing with PR creation...")

    # Push to remote
    print("Pushing to remote...")
    if not push_to_remote(branch):
        sys.exit(1)

    # Generate PR body
    print("Generating PR body...")
    pr_body = None
    if not args.no_ollama:
        print("Checking for Ollama...")
        if is_ollama_running():
            print("Ollama is running. Generating PR body...")
            model = args.model or get_ollama_model()
            pr_body = generate_pr_body_with_ollama(issue_title, issue_body, model)
            if pr_body:
                print("Generated PR body with Ollama")
        else:
            print("Ollama not available. Using placeholder PR body.")

    if not pr_body:
        pr_body = create_placeholder_pr_body(issue_id, issue_title, issue_body)

    # Append Closes directive if not already present
    if f"Closes #{issue_id}" not in pr_body:
        pr_body += f"\n\nCloses #{issue_id}"

    # Create PR
    check_gh_available()
    print("Creating PR...")
    pr_url = create_pr(owner, repo, branch, default_branch, f"[Issue #{issue_id}] {issue_title}", pr_body)

    if pr_url:
        print(f"\n✓ PR created successfully!")
        print(f"  {pr_url}")
    else:
        print("Failed to create PR", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()