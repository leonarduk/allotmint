import requests

from backend.integrations.moneyhub_api import MoneyhubClient


class FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_fetch_transactions_follows_next_link(monkeypatch):
    responses = iter(
        [
            FakeResponse({"data": [{"id": "tx-1"}], "links": {"next": "/transactions?page=2"}}),
            FakeResponse({"data": [{"id": "tx-2"}]}),
        ]
    )
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs["params"]))
        return next(responses)

    monkeypatch.setattr(requests, "get", fake_get)

    result = MoneyhubClient("id", "secret").fetch_transactions("token", account_id="account-1")

    assert result == [{"id": "tx-1"}, {"id": "tx-2"}]
    assert calls == [
        ("https://api.moneyhub.co.uk/transactions", {"accountId": "account-1"}),
        ("https://api.moneyhub.co.uk/transactions?page=2", {}),
    ]


def test_fetch_transactions_follows_link_header(monkeypatch):
    responses = iter(
        [
            FakeResponse(
                {"transactions": [{"id": "tx-1"}]},
                {"Link": '<https://api.moneyhub.co.uk/transactions?page=2>; rel="next"'},
            ),
            FakeResponse({"transactions": [{"id": "tx-2"}]}),
        ]
    )
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: next(responses))

    result = MoneyhubClient("id", "secret").fetch_transactions("token")

    assert [transaction["id"] for transaction in result] == ["tx-1", "tx-2"]


def test_fetch_transactions_stops_at_max_pages(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        page = len(calls)
        return FakeResponse({"data": [{"id": f"tx-{page}"}], "next": f"/transactions?page={page + 1}"})

    monkeypatch.setattr(requests, "get", fake_get)

    result = MoneyhubClient("id", "secret").fetch_transactions("token", max_pages=2)

    assert [transaction["id"] for transaction in result] == ["tx-1", "tx-2"]
    assert len(calls) == 2


def test_fetch_transactions_stops_on_repeated_url(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse({"data": [{"id": "tx-1"}], "next": "/transactions"})

    monkeypatch.setattr(requests, "get", fake_get)

    result = MoneyhubClient("id", "secret").fetch_transactions("token")

    assert result == [{"id": "tx-1"}]
    assert len(calls) == 1


def test_fetch_transactions_keeps_single_page_behavior(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse([{"id": "tx-1"}]))

    result = MoneyhubClient("id", "secret").fetch_transactions("token")

    assert result == [{"id": "tx-1"}]
