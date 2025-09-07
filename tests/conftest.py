import os
from pathlib import Path

import boto3
import pytest

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATA_ROOT", str(Path(__file__).resolve().parent.parent / "data"))

from backend.config import config


@pytest.fixture(scope="session", autouse=True)
def enable_offline_mode():
    """Force backend to run in offline mode for all tests."""
    previous = config.offline_mode
    config.offline_mode = True
    try:
        yield
    finally:
        config.offline_mode = previous


@pytest.fixture(autouse=True)
def mock_google_verify(monkeypatch):
    """Stub Google ID token verification for tests."""

    from fastapi import HTTPException
    from backend import auth

    def fake_verify(token: str):
        if token == "good":
            return "lucy@example.com"
        if token == "other":
            raise HTTPException(status_code=403, detail="Unauthorized email")
        raise HTTPException(status_code=401, detail="Invalid token")

    monkeypatch.setattr(auth, "verify_google_token", fake_verify)


@pytest.fixture
def quotes_table(monkeypatch):
    """In-memory DynamoDB table for quote tests."""

    items = []

    class FakeTable:
        def put_item(self, Item):
            items.append(Item)

        def scan(self):
            return {"Items": items, "Count": len(items)}

    table = FakeTable()

    class FakeResource:
        def Table(self, _name):
            return table

    original_resource = boto3.resource

    def fake_resource(service_name, *args, **kwargs):
        if service_name == "dynamodb":
            return FakeResource()
        return original_resource(service_name, *args, **kwargs)

    monkeypatch.setattr(boto3, "resource", fake_resource)

    return table
