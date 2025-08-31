import boto3
import pytest

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
