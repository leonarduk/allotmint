from typing import Any

import pytest
from fastapi import HTTPException

import backend.routes.instrument_admin as instrument_admin

pytestmark = pytest.mark.asyncio


class _GroupStore:
    def __init__(self, initial: list[str] | None = None) -> None:
        self.groups = list(initial or [])

    def load_groups(self) -> list[str]:
        return list(self.groups)

    def add_group(self, name: str) -> list[str]:
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("blank")
        if trimmed.casefold() in (g.casefold() for g in self.groups):
            return list(self.groups)
        self.groups.append(trimmed)
        return list(self.groups)


@pytest.fixture
def path_states(monkeypatch: pytest.MonkeyPatch, tmp_path) -> dict[tuple[str, str], Any]:
    states: dict[tuple[str, str], Any] = {}

    class PathStub:
        def __init__(self, key: tuple[str, str]) -> None:
            self.key = key
            # create a backing path under tmp_path to mirror the real implementation
            self.path = tmp_path / f"{key[0]}_{key[1]}.json"

        def exists(self) -> bool:
            state = states.get(self.key, False)
            if isinstance(state, Exception):
                raise state
            if callable(state):
                return state()
            return bool(state)

    def fake_instrument_meta_path(ticker: str, exchange: str) -> PathStub:
        return PathStub((ticker, exchange))

    monkeypatch.setattr(instrument_admin, "instrument_meta_path", fake_instrument_meta_path)
    return states


@pytest.fixture
def save_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    saved: list[tuple[str, str, dict[str, Any]]] = []
    deleted: list[tuple[str, str]] = []

    def fake_save(ticker: str, exchange: str, payload: dict[str, Any]) -> None:
        saved.append((ticker, exchange, dict(payload)))

    def fake_delete(ticker: str, exchange: str) -> None:
        deleted.append((ticker, exchange))

    monkeypatch.setattr(instrument_admin, "save_instrument_meta", fake_save)
    monkeypatch.setattr(instrument_admin, "delete_instrument_meta", fake_delete)
    return {"saved": saved, "deleted": deleted}


async def test_list_group_labels_merges_trimmed_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ["Alpha"]
    monkeypatch.setattr(instrument_admin.instrument_groups, "load_groups", lambda: list(store))
    monkeypatch.setattr(
        instrument_admin,
        "list_instruments",
        lambda: [
            {"grouping": "  Beta  "},
            {"grouping": "Gamma "},
            {"grouping": ""},
            {"grouping": None},
            {"grouping": 123},
        ],
    )

    labels = await instrument_admin.list_group_labels()

    assert labels == sorted(["Alpha", "Beta", "Gamma"], key=str.casefold)


async def test_create_group_handles_duplicates_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _GroupStore(["Alpha"])
    monkeypatch.setattr(instrument_admin.instrument_groups, "load_groups", store.load_groups)
    monkeypatch.setattr(instrument_admin.instrument_groups, "add_group", store.add_group)

    created = await instrument_admin.create_group({"name": " Beta "})
    assert created["status"] == "created"
    assert created["group"] == "Beta"
    assert "Beta" in created["groups"]

    duplicate = await instrument_admin.create_group({"name": " alpha "})
    assert duplicate["status"] == "exists"
    assert duplicate["group"] == "Alpha"

    with pytest.raises(HTTPException) as exc_non_str:
        await instrument_admin.create_group({"name": 123})
    assert exc_non_str.value.status_code == 400

    with pytest.raises(HTTPException) as exc_blank:
        await instrument_admin.create_group({"name": "   "})
    assert exc_blank.value.status_code == 400


async def test_create_instrument_validation_and_persistence(
    path_states: dict[tuple[str, str], Any], save_calls: dict[str, Any]
) -> None:
    path_states[("AAA", "NYSE")] = True
    with pytest.raises(HTTPException) as exc_exists:
        await instrument_admin.create_instrument("NYSE", "AAA", {})
    assert exc_exists.value.status_code == 409

    path_states[("BBB", "NYSE")] = False
    with pytest.raises(HTTPException) as exc_mismatch:
        await instrument_admin.create_instrument("NYSE", "BBB", {"ticker": "WRONG"})
    assert exc_mismatch.value.status_code == 400

    payload = {"name": "Example"}
    path_states[("CCC", "NYSE")] = False
    result = await instrument_admin.create_instrument("NYSE", "CCC", payload)
    assert result == {"status": "created"}
    assert save_calls["saved"][-1] == ("CCC", "NYSE", payload)


async def test_update_instrument_errors_and_merges(
    monkeypatch: pytest.MonkeyPatch,
    path_states: dict[tuple[str, str], Any],
    save_calls: dict[str, Any],
) -> None:
    path_states[("AAA", "NYSE")] = False
    with pytest.raises(HTTPException) as exc_missing:
        await instrument_admin.update_instrument("NYSE", "AAA", {})
    assert exc_missing.value.status_code == 404

    path_states[("AAA", "NYSE")] = True

    def load_meta(exchange: str, ticker: str) -> dict[str, Any]:
        return {"ticker": f"{ticker}.{exchange}", "exchange": exchange, "name": "Existing", "meta": "keep"}

    monkeypatch.setattr(instrument_admin, "_load_meta_for_update", load_meta)

    with pytest.raises(HTTPException) as exc_ticker:
        await instrument_admin.update_instrument("NYSE", "AAA", {"ticker": "OTHER.NYSE"})
    assert exc_ticker.value.status_code == 400

    with pytest.raises(HTTPException) as exc_exchange:
        await instrument_admin.update_instrument("NYSE", "AAA", {"exchange": "LSE"})
    assert exc_exchange.value.status_code == 400

    update = {"name": "Updated", "extra": 5}
    response = await instrument_admin.update_instrument("NYSE", "AAA", update)
    assert response == {"status": "updated"}

    saved_entry = save_calls["saved"][-1]
    assert saved_entry[0] == "AAA"
    assert saved_entry[1] == "NYSE"
    assert saved_entry[2] == {
        "ticker": "AAA.NYSE",
        "exchange": "NYSE",
        "name": "Updated",
        "meta": "keep",
        "extra": 5,
    }


async def test_refresh_instrument_offline_guard(
    monkeypatch: pytest.MonkeyPatch,
    path_states: dict[tuple[str, str], Any],
    save_calls: dict[str, Any],
) -> None:
    path_states[("AAA", "NYSE")] = True

    def original_fetch(_: str) -> dict[str, Any]:  # pragma: no cover - guard prevents execution
        raise AssertionError("should not fetch when offline")

    monkeypatch.setattr(instrument_admin, "_ORIGINAL_FETCH_METADATA", original_fetch, raising=False)
    monkeypatch.setattr(instrument_admin, "_fetch_metadata_from_yahoo", original_fetch, raising=False)
    monkeypatch.setattr(instrument_admin.config, "offline_mode", True)

    with pytest.raises(HTTPException) as exc:
        await instrument_admin.refresh_instrument("NYSE", "AAA")
    assert exc.value.status_code == 503
    assert save_calls["saved"] == []


async def test_refresh_instrument_preview_shows_diff_without_saving(
    monkeypatch: pytest.MonkeyPatch,
    path_states: dict[tuple[str, str], Any],
    save_calls: dict[str, Any],
) -> None:
    path_states[("BBB", "NYSE")] = True
    monkeypatch.setattr(instrument_admin.config, "offline_mode", False)

    existing = {"ticker": "BBB.NYSE", "exchange": "NYSE", "name": "Old", "instrument_type": "fund"}

    def load_meta(exchange: str, ticker: str) -> dict[str, Any]:
        assert (ticker, exchange) == ("BBB", "NYSE")
        return dict(existing)

    fetched = {"ticker": "BBB.NYSE", "name": "New", "instrumentType": "Equity"}

    monkeypatch.setattr(instrument_admin, "_load_meta_for_update", load_meta)
    monkeypatch.setattr(instrument_admin, "_fetch_metadata_from_yahoo", lambda _: dict(fetched), raising=False)

    response = await instrument_admin.refresh_instrument("NYSE", "BBB")

    assert response["status"] == "preview"
    assert response["changes"]["name"] == {"from": "Old", "to": "New"}
    assert response["metadata"]["instrumentType"] == "Equity"
    assert response["metadata"]["instrument_type"] == "Equity"
    assert save_calls["saved"] == []


async def test_refresh_instrument_persists_when_not_preview(
    monkeypatch: pytest.MonkeyPatch,
    path_states: dict[tuple[str, str], Any],
    save_calls: dict[str, Any],
) -> None:
    path_states[("CCC", "NYSE")] = True
    monkeypatch.setattr(instrument_admin.config, "offline_mode", False)

    def load_meta(exchange: str, ticker: str) -> dict[str, Any]:
        return {"ticker": f"{ticker}.{exchange}", "exchange": exchange, "instrumentType": "Bond"}

    fetched = {"ticker": "CCC.NYSE", "instrument_type": "bond", "currency": "USD"}

    monkeypatch.setattr(instrument_admin, "_load_meta_for_update", load_meta)
    monkeypatch.setattr(instrument_admin, "_fetch_metadata_from_yahoo", lambda _: dict(fetched), raising=False)

    response = await instrument_admin.refresh_instrument("NYSE", "CCC", {"preview": False})

    assert response["status"] == "updated"
    merged = save_calls["saved"][-1][2]
    assert merged["instrument_type"] == "bond"
    assert merged["instrumentType"] == "bond"
    assert merged["currency"] == "USD"


async def test_normalise_group_rejects_invalid_values() -> None:
    with pytest.raises(HTTPException) as exc_type:
        instrument_admin._normalise_group(123)
    assert exc_type.value.status_code == 400

    with pytest.raises(HTTPException) as exc_blank:
        instrument_admin._normalise_group("   ")
    assert exc_blank.value.status_code == 400


async def test_assign_group_validates_and_persists(
    monkeypatch: pytest.MonkeyPatch,
    path_states: dict[tuple[str, str], Any],
    save_calls: dict[str, Any],
) -> None:
    path_states[("DDD", "NYSE")] = False

    def load_meta(exchange: str, ticker: str) -> dict[str, Any]:
        return {"ticker": f"{ticker}.{exchange}", "exchange": exchange}

    added: list[str] = []

    def add_group(name: str) -> list[str]:
        added.append(name)
        return ["Existing", name]

    monkeypatch.setattr(instrument_admin, "_load_meta_for_update", load_meta)
    monkeypatch.setattr(instrument_admin.instrument_groups, "add_group", add_group)

    result = await instrument_admin.assign_group("NYSE", "DDD", {"group": "  Sector  "})

    assert result["status"] == "assigned"
    assert result["group"] == "Sector"
    assert added == ["Sector"]
    saved_entry = save_calls["saved"][-1]
    assert saved_entry[2]["grouping"] == "Sector"

    with pytest.raises(HTTPException):
        await instrument_admin.assign_group("NYSE", "DDD", {"group": 123})

    with pytest.raises(HTTPException):
        await instrument_admin.assign_group("NYSE", "DDD", {"group": "   "})


async def test_clear_group_persists_then_skips_when_absent(
    monkeypatch: pytest.MonkeyPatch,
    path_states: dict[tuple[str, str], Any],
    save_calls: dict[str, Any],
) -> None:
    path_states[("EEE", "NYSE")] = False
    meta_states = [
        {"ticker": "EEE.NYSE", "exchange": "NYSE", "grouping": "Sector"},
        {"ticker": "EEE.NYSE", "exchange": "NYSE"},
    ]

    def load_meta(exchange: str, ticker: str) -> dict[str, Any]:
        state = meta_states.pop(0)
        return dict(state)

    monkeypatch.setattr(instrument_admin, "_load_meta_for_update", load_meta)

    result_first = await instrument_admin.clear_group("NYSE", "EEE")
    assert result_first == {"status": "cleared"}
    first_save_count = len(save_calls["saved"])
    assert save_calls["saved"][-1][2].get("grouping") is None

    result_second = await instrument_admin.clear_group("NYSE", "EEE")
    assert result_second == {"status": "cleared"}
    assert len(save_calls["saved"]) == first_save_count
