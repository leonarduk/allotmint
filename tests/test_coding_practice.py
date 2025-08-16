import json
import pathlib
import os

# moto requires dummy credentials before importing the module
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

import boto3
from moto import mock_aws

# dynamically import the coding_practice module
MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "jd-backend/python/coding_practice.py"
spec = None
if MODULE_PATH.exists():
    import importlib.util

    spec = importlib.util.spec_from_file_location("coding_practice", MODULE_PATH)
    coding_practice = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(coding_practice)
else:  # pragma: no cover - defensive fallback
    raise FileNotFoundError(MODULE_PATH)


@mock_aws
def test_crud_cycle():
    table_name = "JD_CodingPractice"
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    dynamodb.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    # list should be empty
    resp = coding_practice.list_puzzles({}, {})
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == []

    # add a puzzle
    body = {"title": "Two Sum", "description": "Find indices"}
    resp = coding_practice.add_puzzle({"body": json.dumps(body)}, {})
    data = json.loads(resp["body"])
    assert "id" in data and data["title"] == "Two Sum"
    puzzle_id = data["id"]

    # update puzzle
    updated = {"id": puzzle_id, "title": "Two Sum", "description": "Find indices that add up"}
    resp = coding_practice.update_puzzle({"body": json.dumps(updated)}, {})
    assert resp["statusCode"] == 200

    # list should include updated puzzle
    resp = coding_practice.list_puzzles({}, {})
    items = json.loads(resp["body"])
    assert len(items) == 1 and items[0]["description"].startswith("Find")

    # delete puzzle
    resp = coding_practice.delete_puzzle({"pathParameters": {"id": puzzle_id}}, {})
    assert resp["statusCode"] == 200

    # list empty again
    resp = coding_practice.list_puzzles({}, {})
    assert json.loads(resp["body"]) == []
