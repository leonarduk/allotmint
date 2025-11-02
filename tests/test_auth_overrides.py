import asyncio
from types import SimpleNamespace

import pytest

import backend.auth as auth


class FakeRequest:
    def __init__(self):
        self.app = None


def _make_request(**attrs):
    request = SimpleNamespace(**attrs)
    return request


def test_iter_override_mappings_deduplicates_and_orders():
    shared_mapping = {"shared": lambda: "shared"}

    nested_provider = SimpleNamespace(
        dependency_overrides={"nested": lambda: "nested"},
        dependency_overrides_provider=None,
    )
    provider = SimpleNamespace(
        dependency_overrides={"provider": lambda: "provider"},
        dependency_overrides_provider=[nested_provider],
    )
    router = SimpleNamespace(
        dependency_overrides={"router": lambda: "router"},
        dependency_overrides_provider=[provider],
    )
    app = SimpleNamespace(
        router=router,
        dependency_overrides=shared_mapping,
        dependency_overrides_provider=provider,
    )
    request = _make_request(app=app)

    mappings = auth._iter_override_mappings(request)

    assert mappings[0] is shared_mapping
    assert mappings[1] == router.dependency_overrides
    assert any("provider" in mapping for mapping in mappings)
    assert any("nested" in mapping for mapping in mappings)
    # shared mapping returned only once despite appearing on both app and provider
    assert mappings.count(shared_mapping) == 1


@pytest.mark.asyncio
async def test_invoke_override_injects_token_and_request(monkeypatch):
    monkeypatch.setattr(auth, "Request", FakeRequest)

    captured = {}

    def override(request: FakeRequest, token: str):
        captured["request"] = request
        captured["token"] = token
        return "result"

    request = FakeRequest()
    result = await auth._invoke_override(override, request=request, token="abc")

    assert result == "result"
    assert captured == {"request": request, "token": "abc"}


@pytest.mark.asyncio
async def test_invoke_override_supports_async_callables(monkeypatch):
    async def override(token: str | None = None):
        await asyncio.sleep(0)
        return token

    request = FakeRequest()
    result = await auth._invoke_override(override, request=request, token="xyz")
    assert result == "xyz"


def test_find_override_matches_unwrapped_functions(monkeypatch):
    def dependency():
        return "dependency"

    def override():
        return "override"

    def wrapped_dependency():
        return dependency()

    wrapped_dependency.__module__ = dependency.__module__
    wrapped_dependency.__qualname__ = dependency.__qualname__

    mapping = {wrapped_dependency: override}
    monkeypatch.setattr(auth, "_iter_override_mappings", lambda request: [mapping])

    result = auth._find_override(SimpleNamespace(), dependency)
    assert result is override


@pytest.mark.asyncio
async def test_resolve_current_user_override_invokes_override(monkeypatch):
    async def override(token: str | None = None):
        return f"override:{token}"

    monkeypatch.setattr(auth, "_find_override", lambda request, dependency: override)

    has_override, result = await auth.resolve_current_user_override(
        SimpleNamespace(), token="token"
    )

    assert has_override is True
    assert result == "override:token"


@pytest.mark.asyncio
async def test_resolve_current_user_override_handles_missing(monkeypatch):
    monkeypatch.setattr(auth, "_find_override", lambda request, dependency: None)

    has_override, result = await auth.resolve_current_user_override(SimpleNamespace())

    assert has_override is False
    assert result is None
