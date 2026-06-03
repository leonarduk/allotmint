"""Extract and validate the AI review verdict from review output."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def extract_verdict(review_text: str) -> str | None:
    """Extract the verdict from review text.

    Looks for verdict lines in the format:
    - `**APPROVE**` — ...
    - `**REQUEST CHANGES**` — ...

    Returns 'APPROVE' or 'REQUEST CHANGES' if found, None otherwise.
    """
    # Look for verdict lines that match the expected format
    match = re.search(r'\*\*(APPROVE|REQUEST CHANGES)\*\*', review_text)
    if match:
        return match.group(1)
    return None


def main(review_file: str, provider_name: str) -> int:
    """Read review file, extract verdict, and exit with appropriate status.

    Args:
        review_file: Path to the file containing the review text.
        provider_name: Name of the provider (Claude or GPT) for output messages.

    Returns:
        0 if verdict is APPROVE, 1 if REQUEST CHANGES or no verdict found.
    """
    try:
        review_text = Path(review_file).read_text()
    except FileNotFoundError:
        print(f"ERROR: Review file not found: {review_file}", file=sys.stderr)
        return 1

    if not review_text.strip():
        print(f"ERROR: {provider_name} review output was empty", file=sys.stderr)
        return 1

    verdict = extract_verdict(review_text)

    if verdict == "APPROVE":
        print(f"✓ {provider_name} review: APPROVED")
        return 0

    if verdict == "REQUEST CHANGES":
        print(f"✗ {provider_name} review: CHANGES REQUESTED")
        return 1

    print(
        f"ERROR: {provider_name} review did not include a valid verdict. "
        "Expected '**APPROVE**' or '**REQUEST CHANGES**' in the review.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} <review_file> <provider_name>",
            file=sys.stderr,
        )
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
