"""Allotmint-specific RepoProfile for the shared cicaid_devtools advisory review prompt.

Shared by claude_review.py, gpt_review.py, and deepseek_review.py so the review
persona/stack description/repo-specific safety checks stay identical across all
three providers without each script re-declaring the same profile.
"""

from __future__ import annotations

from cicaid_devtools.lib.review_common import RepoProfile

ALLOTMINT_REPO_PROFILE = RepoProfile(
    name="allotmint",
    persona="a family investment management app.",
    stack_paragraph=(
        "The stack is Python/FastAPI backend + React/Vite TypeScript frontend + "
        "AWS Lambda/CDK infrastructure.\n"
        "Key constraints: preserve portfolio/compliance correctness, keep "
        "backend/frontend contracts aligned,\n"
        "and avoid regressions in CI/deployment workflows."
    ),
    diff_file_types=(
        "Python, TypeScript, JavaScript, JSON, Markdown, HTML, config files, "
        "shell scripts (.sh), PowerShell scripts (.ps1)"
    ),
    dimension_2_body=(
        "Blocking only: incorrect behaviour, unhandled edge cases, off-by-one errors, or\n"
        "security/data-loss risks. For documentation PRs: factual errors or dangerously\n"
        "misleading statements."
    ),
    dimension_3_title="API, data, and workflow safety",
    dimension_3_body=(
        "- Backend/frontend payload shapes misaligned?\n"
        "- Could this break local smoke tests, deployment workflows, or repo scripts?\n"
        "- Secrets, permissions, or CI assumptions mishandled?"
    ),
    known_facts=(
        "- **`actions/checkout@v6` and `actions/setup-node@v6` are correct.** Dependabot "
        "bumped both from\n"
        "  v4 to v6 in PRs #2954/#2953; they are the repo-wide convention. Do not flag them as\n"
        "  non-existent or wrong.\n"
        "- **`api.getVarBreakdown()` returns camelCase keys** (`varDate`, `varLossPercent`, "
        "`scenarios`,\n"
        "  `breakdown`). The function in `frontend/src/api.ts` transforms the snake_case "
        "backend response\n"
        "  before returning. Test mocks that use camelCase for this function are correct.\n"
        "- **`recomputeValueAtRisk` is fire-and-forget** in `ValueAtRisk.tsx`. After calling "
        "it, the\n"
        "  component does not re-fetch `getValueAtRisk`; a period change or page refresh "
        "triggers the next\n"
        "  fetch. Tests asserting `getValueAtRisk` is called only once after a recompute are "
        "correct.\n"
        "- **`frontend/package-lock.json` contains Linux-specific optional peer deps** (e.g.\n"
        "  `@emnapi/core`, `@emnapi/runtime`) that do not appear when the lock file is "
        "regenerated on\n"
        "  Windows. Do not suggest regenerating or normalising the lock file on a non-Linux "
        "machine."
    ),
)
