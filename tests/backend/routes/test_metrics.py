import pytest
from fastapi import HTTPException

from backend.common.errors import OwnerNotFoundError
from backend.routes import metrics


@pytest.mark.asyncio
async def test_get_metrics_returns_cached_payload(monkeypatch):
    cached_payload = {"turnover": 0.42}

    def stub_load(owner: str):
        assert owner == "alex"
        return cached_payload

    def stub_compute(owner: str):
        raise AssertionError("compute_and_store_metrics should not be called when cache has data")

    monkeypatch.setattr(metrics, "load_metrics", stub_load)
    monkeypatch.setattr(metrics, "compute_and_store_metrics", stub_compute)

    result = await metrics.get_metrics("alex")

    assert result == cached_payload


@pytest.mark.asyncio
async def test_get_metrics_computes_when_cache_empty(monkeypatch):
    sentinel = {"generated": True}

    def stub_load(owner: str):
        assert owner == "alex"
        return {}

    def stub_compute(owner: str):
        assert owner == "alex"
        return sentinel

    monkeypatch.setattr(metrics, "load_metrics", stub_load)
    monkeypatch.setattr(metrics, "compute_and_store_metrics", stub_compute)

    result = await metrics.get_metrics("alex")

    assert result is sentinel


@pytest.mark.asyncio
async def test_get_metrics_raises_http_not_found(monkeypatch):
    def stub_load(owner: str):
        raise FileNotFoundError

    stub = {"called": False}

    def stub_raise_owner_not_found():
        stub["called"] = True
        raise OwnerNotFoundError

    monkeypatch.setattr(metrics, "load_metrics", stub_load)
    monkeypatch.setattr(metrics, "raise_owner_not_found", stub_raise_owner_not_found)

    with pytest.raises(HTTPException) as exc:
        await metrics.get_metrics("alex")

    assert exc.value.status_code == 404
    assert stub["called"]
