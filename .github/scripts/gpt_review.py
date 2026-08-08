"""GPT AI code review script called by gpt-pr-review.yml.

This module delegates entirely to ``cidaid_devtools.lib.gpt_review``,
passing an allotmint-specific ``RepoProfile`` so the prompt persona, stack
description, known facts, and dimension‑3 safety checks match allotmint
rather than cicaid's defaults.
"""

from __future__ import annotations

import sys

from cicaid_devtools.lib.gpt_review import main as _cidaid_main
from cicaid_devtools.lib.review_common import RepoProfile

ALLOTMINT_REPO_PROFILE = RepoProfile(
    name="allotmint",
    persona="a family investment management app",
    stack_paragraph=(
        "The stack is Python/FastAPI backend + React/Vite TypeScript frontend "
        "+ AWS Lambda/CDK infrastructure.\n"
        "Key constraints: preserve portfolio/compliance correctness, keep "
        "backend/frontend contracts aligned, and avoid regressions in "
        "CI/deployment workflows."
    ),
    diff_file_types=(
        "Python, TypeScript, JavaScript, JSON, Markdown, HTML, "
        "config files, shell scripts (.sh), PowerShell scripts (.ps1)"
    ),
    dimension_2_body=(
        "Blocking only: incorrect behaviour, unhandled edge cases, off-by-one "
        "errors, or security/data-loss risks. For documentation PRs: factual "
        "errors or dangerously misleading statements."
    ),
    dimension_3_title="API, data, and workflow safety",
    dimension_3_body=(
        "- Backend/frontend payload shapes misaligned?\n"
        "- Could this break local smoke tests, deployment workflows, or repo "
        "scripts?\n"
        "- Secrets, permissions, or CI assumptions mishandled?"
    ),
    known_facts=(
        "- **`actions/checkout@v6` and `actions/setup-node@v6` are correct.** "
        "Dependabot bumped both from v4 to v6 in PRs #2954/#2953; they are "
        "the repo-wide convention. Do not flag them as non-existent or wrong.\n"
        "- **`api.getVarBreakdown()` returns camelCase keys** (`varDate`, "
        "`varLossPercent`, `scenarios`, `breakdown`). The function in "
        "`frontend/src/api.ts` transforms the snake_case backend response "
        "before returning. Test mocks that use camelCase for this function "
        "are correct.\n"
        "- **`recomputeValueAtRisk` is fire-and-forget** in "
        "`ValueAtRisk.tsx`. After calling it, the component does not re-fetch "
        "`getValueAtRisk`; a period change or page refresh triggers the next "
        "fetch. Tests asserting `getValueAtRisk` is called only once after a "
        "recompute are correct.\n"
        "- **`frontend/package-lock.json` contains Linux-specific optional "
        "peer deps** (e.g. `@emnapi/core`, `@emnapi/runtime`) that do not "
        "appear when the lock file is regenerated on Windows. Do not suggest "
        "regenerating or normalising the lock file on a non-Linux machine."
    ),
)


def main() -> int:
    """Run the advisory GPT review flow with the allotmint repo profile."""
    return _cidaid_main(repo_profile=ALLOTMINT_REPO_PROFILE)


if __name__ == "__main__":
    raise SystemExit(main())
