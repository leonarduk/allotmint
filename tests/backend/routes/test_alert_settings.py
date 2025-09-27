from __future__ import annotations

import anyio
import pytest
from fastapi import FastAPI, Request
from starlette.requests import Request as StarletteRequest

from backend.auth import get_current_user
from backend.routes import alert_settings


def _make_request(app: FastAPI) -> Request:
    async def receive() -> dict[str, object]:
        return {"type": "http.request"}

    scope = {"type": "http", "app": app, "headers": []}
    return StarletteRequest(scope, receive)  # type: ignore[return-value]


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(alert_settings.router)
    return app


@pytest.mark.anyio("asyncio")
async def test_resolve_identity_prefers_overrides(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: "override-user"
    request = _make_request(app)

    identity = await alert_settings._resolve_identity(request, None)

    assert identity == "override-user"


@pytest.mark.anyio("asyncio")
async def test_resolve_identity_awaits_coroutine_overrides(app: FastAPI) -> None:
    async def override() -> str:
        await anyio.sleep(0)
        return "async-user"

    app.dependency_overrides[get_current_user] = override
    request = _make_request(app)

    identity = await alert_settings._resolve_identity(request, None)

    assert identity == "async-user"


@pytest.mark.anyio("asyncio")
async def test_resolve_identity_defaults_to_demo(app: FastAPI) -> None:
    request = _make_request(app)

    identity = await alert_settings._resolve_identity(request, None)

    assert identity == alert_settings.DEMO_IDENTITY


@pytest.mark.anyio("asyncio")
async def test_get_threshold_uses_resolved_identity(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_get_user_threshold(user: str) -> float:
        calls.append(user)
        return 3.14

    monkeypatch.setattr(
        alert_settings.alert_utils, "get_user_threshold", fake_get_user_threshold
    )

    app.dependency_overrides[get_current_user] = lambda: "resolved-user"
    request = _make_request(app)

    response = await alert_settings.get_threshold(
        user="resolved-user", request=request, current_user=None
    )

    assert calls == ["resolved-user"]
    assert response == {"threshold": 3.14}


@pytest.mark.anyio("asyncio")
async def test_set_threshold_uses_resolved_identity(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, float]] = []

    def fake_set_user_threshold(user: str, threshold: float) -> None:
        calls.append((user, threshold))

    monkeypatch.setattr(
        alert_settings.alert_utils, "set_user_threshold", fake_set_user_threshold
    )

    app.dependency_overrides[get_current_user] = lambda: "resolved-user"
    request = _make_request(app)
    payload = alert_settings.ThresholdPayload(threshold=1.23)

    response = await alert_settings.set_threshold(
        user="resolved-user", payload=payload, request=request, current_user=None
    )

    assert calls == [("resolved-user", 1.23)]
    assert response == {"threshold": 1.23}


@pytest.mark.anyio("asyncio")
async def test_get_threshold_owner_mismatch(app: FastAPI) -> None:
    request = _make_request(app)

    with pytest.raises(alert_settings.HTTPException) as excinfo:
        await alert_settings.get_threshold(
            user="alice", request=request, current_user="bob"
        )

    assert excinfo.value.status_code == alert_settings.status.HTTP_403_FORBIDDEN


@pytest.mark.anyio("asyncio")
async def test_set_threshold_owner_mismatch(app: FastAPI) -> None:
    request = _make_request(app)
    payload = alert_settings.ThresholdPayload(threshold=5.0)

    with pytest.raises(alert_settings.HTTPException) as excinfo:
        await alert_settings.set_threshold(
            user="alice", payload=payload, request=request, current_user="bob"
        )

    assert excinfo.value.status_code == alert_settings.status.HTTP_403_FORBIDDEN
