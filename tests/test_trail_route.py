import importlib
import asyncio

import pytest

from backend.routes import trail as trail_module


def test_complete_task_demo(monkeypatch):
    monkeypatch.setattr(trail_module.config, "disable_auth", True)
    importlib.reload(trail_module)
    monkeypatch.setattr(trail_module.trail, "mark_complete", lambda user, tid: ["done"])
    result = asyncio.run(trail_module.complete_task("t1"))
    assert result == {"tasks": ["done"]}


def test_complete_task_authenticated(monkeypatch):
    monkeypatch.setattr(trail_module.config, "disable_auth", False)
    importlib.reload(trail_module)
    monkeypatch.setattr(trail_module.trail, "mark_complete", lambda user, tid: ["ok"])
    result = asyncio.run(trail_module.complete_task("t2", current_user="bob"))
    assert result == {"tasks": ["ok"]}
