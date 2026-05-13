"""
Regression guard: Lambda-adjacent modules must not make AWS calls at import time.

Uses AST inspection so the check is instant (no module reload, no file I/O).
This would have caught the cold-start 503 in #2975, where _load_snapshot() was
called at module scope in portfolio_utils.py and made a blocking S3 GetObject
during Lambda init, exceeding the 10 s init limit.
"""
import ast
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"


def _module_level_calls(rel_path: str) -> list[tuple[str, int]]:
    """Return (callee_name, lineno) for every bare function call at module scope."""
    src = (_BACKEND_ROOT / rel_path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    hits: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = func.id if isinstance(func, ast.Name) else None
            if name:
                hits.append((name, node.lineno))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = func.id if isinstance(func, ast.Name) else None
            if name:
                hits.append((name, node.lineno))
    return hits


# Functions that are known to make AWS calls and must never run at module scope.
_AWS_FUNCTIONS = {"_load_snapshot"}


@pytest.mark.parametrize("rel_path", [
    "common/portfolio_utils.py",
])
def test_no_aws_call_at_module_scope(rel_path):
    """No AWS-touching function may be called at module scope."""
    hits = _module_level_calls(rel_path)
    offenders = [(fn, ln) for fn, ln in hits if fn in _AWS_FUNCTIONS]
    if offenders:
        details = ", ".join(f"{fn}() at line {ln}" for fn, ln in offenders)
        pytest.fail(
            f"{rel_path}: module-scope AWS call(s) found — {details}. "
            "S3 access must be deferred to the ASGI lifespan to avoid "
            "Lambda cold-start timeouts (see #2975)."
        )
