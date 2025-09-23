import importlib
import asyncio

import pytest

from backend.routes import trail as trail_module


def test_complete_task_demo_wraps_list_response(monkeypatch):
    monkeypatch.setattr(trail_module.config, "disable_auth", True)
    importlib.reload(trail_module)
    monkeypatch.setattr(trail_module.trail, "mark_complete", lambda user, tid: ["done"])
    result = asyncio.run(trail_module.complete_task("t1"))
    assert result == {"tasks": ["done"]}


def test_complete_task_demo_preserves_full_response(monkeypatch):
    monkeypatch.setattr(trail_module.config, "disable_auth", True)
    importlib.reload(trail_module)
    payload = {"tasks": ["existing"], "xp": 10}

    def _mark_complete(user, tid):
        return payload

    monkeypatch.setattr(trail_module.trail, "mark_complete", _mark_complete)
    result = asyncio.run(trail_module.complete_task("t2"))
    assert result is payload


def test_complete_task_authenticated_wraps_list_response(monkeypatch):
    monkeypatch.setattr(trail_module.config, "disable_auth", False)
    importlib.reload(trail_module)
    monkeypatch.setattr(trail_module.trail, "mark_complete", lambda user, tid: ["ok"])
    result = asyncio.run(trail_module.complete_task("t3", current_user="bob"))
    assert result == {"tasks": ["ok"]}


def test_complete_task_authenticated_preserves_full_response(monkeypatch):
    monkeypatch.setattr(trail_module.config, "disable_auth", False)
    importlib.reload(trail_module)
    payload = {"tasks": ["task"], "streak": 3}

    def _mark_complete(user, tid):
        return payload

    monkeypatch.setattr(trail_module.trail, "mark_complete", _mark_complete)
    result = asyncio.run(trail_module.complete_task("t4", current_user="alice"))
    assert result is payload

def test_complete_task_demo_passthrough(monkeypatch):
    monkeypatch.setattr(trail_module.config, "disable_auth", True)
    importlib.reload(trail_module)

    payload = {"tasks": ["already"], "xp": 123}
    monkeypatch.setattr(trail_module.trail, "mark_complete", lambda user, tid: payload)

    result = asyncio.run(trail_module.complete_task("t3"))
    assert result is payload


def test_complete_task_authenticated_passthrough(monkeypatch):
    monkeypatch.setattr(trail_module.config, "disable_auth", False)
    importlib.reload(trail_module)

    payload = {"tasks": ["exists"], "streak": 5}
    monkeypatch.setattr(trail_module.trail, "mark_complete", lambda user, tid: payload)


    result = asyncio.run(trail_module.complete_task("t4", current_user="alice"))
    assert result is payload
