import asyncio
import functools
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


def test_iter_override_mappings_handles_missing_app():
    class KeylessRequest:
        def __getattr__(self, name: str):
            if name == "app":
                raise KeyError(name)
            raise AttributeError(name)

    request = KeylessRequest()

    mappings = auth._iter_override_mappings(request)  # type: ignore[arg-type]

    assert mappings == []


def test_iter_override_mappings_accepts_gettable_objects():
    class Gettable:
        def __init__(self, data: dict):
            self._data = data

        def get(self, key, default=None):
            return self._data.get(key, default)

        def items(self):
            return self._data.items()

    request = _make_request(
        app=SimpleNamespace(
            router=None,
            dependency_overrides=Gettable({}),
            dependency_overrides_provider=SimpleNamespace(
                dependency_overrides=Gettable({}),
                dependency_overrides_provider=(SimpleNamespace(dependency_overrides=Gettable({}), dependency_overrides_provider=None),),
            ),
        )
    )

    mappings = auth._iter_override_mappings(request)

    assert len(mappings) >= 2
    assert all(hasattr(mapping, "get") for mapping in mappings)


def test_iter_override_mappings_ignores_non_mapping_candidates():
    request = _make_request(
        app=SimpleNamespace(
            router=None,
            dependency_overrides=object(),
            dependency_overrides_provider=None,
        )
    )

    assert auth._iter_override_mappings(request) == []


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


@pytest.mark.asyncio
async def test_invoke_override_handles_request_annotations(monkeypatch):
    class BaseRequest:
        pass

    class AnnotatedRequest(BaseRequest):
        pass

    monkeypatch.setattr(auth, "Request", BaseRequest)

    captured: dict[str, object] = {}

    def override(pos_only="default", /, request=None, *, token, annotated: AnnotatedRequest):
        captured.update({
            "pos_only": pos_only,
            "request": request,
            "token": token,
            "annotated": annotated,
        })
        return "done"

    request = AnnotatedRequest()
    result = await auth._invoke_override(override, request=request, token="tok")

    assert result == "done"
    assert captured == {
        "pos_only": "default",
        "request": request,
        "token": "tok",
        "annotated": request,
    }


def test_find_override_matches_unwrapped_functions(monkeypatch):
    def dependency():
        return "dependency"

    def override():
        return "override"

    @functools.wraps(dependency)
    def wrapped_dependency():
        return dependency()

    mapping = {wrapped_dependency: override}
    monkeypatch.setattr(auth, "_iter_override_mappings", lambda request: [mapping])

    result = auth._find_override(SimpleNamespace(), dependency)
    assert result is override


def test_find_override_uses_mapping_get(monkeypatch):
    def dependency():
        return "dep"

    def override():
        return "override"

    class MappingWithGet(dict):
        def get(self, key, default=None):
            if key is dependency:
                return override
            return super().get(key, default)

    monkeypatch.setattr(auth, "_iter_override_mappings", lambda request: [MappingWithGet()])

    result = auth._find_override(SimpleNamespace(), dependency)

    assert result is override


def test_find_override_skips_non_callable_items(monkeypatch):
    class MappingLike(dict):
        items = []

    mapping = MappingLike()
    monkeypatch.setattr(auth, "_iter_override_mappings", lambda request: [mapping])

    result = auth._find_override(SimpleNamespace(), lambda: None)

    assert result is None


def test_find_override_returns_none_for_missing_identity(monkeypatch):
    class CallableWithoutIdentity:
        def __call__(self):  # pragma: no cover - not invoked
            return None

    dependency = CallableWithoutIdentity()
    setattr(dependency, "__module__", None)
    setattr(dependency, "__qualname__", None)
    monkeypatch.setattr(auth, "_iter_override_mappings", lambda request: [])

    assert auth._find_override(SimpleNamespace(), dependency) is None


def test_find_override_matches_direct_dependency(monkeypatch):
    def dependency():
        return "dep"

    def override():
        return "override"

    class MappingNoGet(dict):
        def get(self, key, default=None):
            return None

    mapping = MappingNoGet({dependency: override})
    monkeypatch.setattr(auth, "_iter_override_mappings", lambda request: [mapping])

    assert auth._find_override(SimpleNamespace(), dependency) is override


def test_find_override_matches_via_unwrapped_identity(monkeypatch):
    def dependency():
        return "dep"

    def override():
        return "override"

    def alias():
        return dependency()

    alias.__module__ = dependency.__module__
    alias.__qualname__ = dependency.__qualname__

    def make_wrapper(target):
        def wrapper():
            return target()

        wrapper.__wrapped__ = target
        return wrapper

    declared_dependency = make_wrapper(alias)

    mapping = {declared_dependency: override}
    monkeypatch.setattr(auth, "_iter_override_mappings", lambda request: [mapping])

    assert auth._find_override(SimpleNamespace(), dependency) is override


def test_find_override_matches_via_unwrap_target(monkeypatch):
    def dependency():
        return "dep"

    def override():
        return "override"

    def wrapper():
        return dependency()

    wrapper.__wrapped__ = dependency

    mapping = {wrapper: override}
    monkeypatch.setattr(auth, "_iter_override_mappings", lambda request: [mapping])

    assert auth._find_override(SimpleNamespace(), dependency) is override


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
