"""Run cicaid's issue reviewer with a bounded interactive feedback loop.

The implementation of the review workflow lives in ``cicaid-devtools``.  This
small compatibility entry point applies AllotMint's feedback-round safety
limit without duplicating that shared workflow.
"""

from collections.abc import Callable

from cicaid_devtools import review_issue

MAX_FEEDBACK_RETRIES = 5

Disposition = tuple[str, str | None]


def limited_disposition_prompt(
    prompt: Callable[[], Disposition],
) -> Callable[[], Disposition]:
    """Wrap *prompt* so no more than the allowed feedback rounds are accepted."""
    feedback_retries = 0

    def prompt_with_limit() -> Disposition:
        nonlocal feedback_retries
        action, feedback = prompt()
        if action != "retry":
            return action, feedback

        if feedback_retries >= MAX_FEEDBACK_RETRIES:
            review_issue.logger.error(
                "Maximum feedback retries reached; aborting without applying the review."
            )
            return "abort", None

        feedback_retries += 1
        return action, feedback

    return prompt_with_limit


def main() -> int:
    """Run the shared issue-review command with bounded feedback retries."""
    original_prompt = review_issue.prompt_for_disposition
    review_issue.prompt_for_disposition = limited_disposition_prompt(original_prompt)
    try:
        return review_issue.main()
    finally:
        review_issue.prompt_for_disposition = original_prompt


if __name__ == "__main__":
    raise SystemExit(main())
