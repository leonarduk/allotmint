from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_test", SCRIPTS_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # review_common.py's ReviewContext is a dataclass with `from __future__ import
    # annotations` (string annotations); dataclasses resolves those via
    # sys.modules[cls.__module__], which requires the module to be registered there
    # before exec_module runs the class body.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def review_common():
    return load_module("review_common")


@pytest.fixture(scope="module")
def extract_verdict_mod():
    return load_module("extract_verdict")


@pytest.mark.parametrize("provider", ["Claude", "GPT", "DeepSeek"])
def test_emit_empty_diff_notice_returns_success(review_common, provider) -> None:
    assert review_common.emit_empty_diff_notice(provider) == 0


@pytest.mark.parametrize("provider", ["Claude", "GPT", "DeepSeek"])
def test_emit_empty_diff_notice_parses_as_skip(
    review_common, extract_verdict_mod, capsys, provider
) -> None:
    """The empty-diff advisory notice must read as SKIP, a pass-like sentinel for "no review performed".

    Prior to the SKIP sentinel, the notice ended with "**APPROVE** — nothing to review",
    which was semantically confusing (as if the reviewer approved the code). Now it uses
    **SKIP** to signal that no diff was available for review. extract_verdict.py treats
    SKIP as a pass (exit 0) for workflow purposes.

    Regression test for #5715/#5721: extract_verdict.py previously treated the empty-diff
    notice as having no valid verdict, which the workflow's fail step reported as
    "CHANGES REQUESTED" even though nothing was actually reviewed.
    """
    review_common.emit_empty_diff_notice(provider)
    notice = capsys.readouterr().out

    assert extract_verdict_mod.extract_verdict(notice) == "SKIP"
