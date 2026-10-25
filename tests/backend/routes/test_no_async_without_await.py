"""Every public ``async def`` in ``backend/routes/`` must actually await (#7689).

FastAPI runs a plain ``def`` handler in its threadpool but an ``async def`` on
the event loop, so an ``async def`` with no ``await`` that does blocking work
(file or network I/O) stalls every other request, ``/health`` included.
PR #7687 converted such handlers to ``def``; this AST check keeps them that way.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROUTES_DIR = Path(__file__).resolve().parents[3] / "backend" / "routes"

# Deliberately async without an await: each entry is (module filename,
# function name) with the reason it is safe on the event loop.
ALLOWLIST = {
    # Returns a copy of an in-memory dict under a threading.Lock held for a
    # dict() call only: no I/O, so a threadpool hop would cost more than it saves.
    ("portfolio.py", "refresh_prices_progress"),
}

_ASYNC_NODES = (ast.Await, ast.AsyncFor, ast.AsyncWith)


def _awaits(func: ast.AsyncFunctionDef) -> bool:
    return any(isinstance(node, _ASYNC_NODES) for node in ast.walk(func))


def _is_async_generator(func: ast.AsyncFunctionDef) -> bool:
    return any(isinstance(node, (ast.Yield, ast.YieldFrom)) for node in ast.walk(func))


def _offenders() -> list[str]:
    found = []
    for path in sorted(ROUTES_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef) or node.name.startswith("_"):
                continue
            if (path.name, node.name) in ALLOWLIST or _awaits(node) or _is_async_generator(node):
                continue
            found.append(f"{path.relative_to(ROUTES_DIR.parent.parent)}:{node.lineno} {node.name}")
    return found


def test_routes_dir_is_scanned():
    assert any(ROUTES_DIR.rglob("*.py"))


def test_no_public_async_route_function_without_await():
    offenders = _offenders()
    assert not offenders, (
        "async def without await runs blocking work on the event loop; make these "
        "plain def (FastAPI runs them in its threadpool) or add an await:\n" + "\n".join(offenders)
    )


def test_allowlist_entries_still_exist_and_still_need_it():
    for filename, name in ALLOWLIST:
        tree = ast.parse((ROUTES_DIR / filename).read_text(encoding="utf-8"))
        funcs = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == name]
        assert funcs, f"stale allowlist entry: {filename}:{name}"
        assert not any(_awaits(f) for f in funcs), f"{filename}:{name} now awaits; drop it from ALLOWLIST"
