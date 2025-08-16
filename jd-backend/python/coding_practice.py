import os
import json
import uuid

import boto3


TABLE_NAME = os.environ.get("CODING_PRACTICE_TABLE", "JD_CodingPractice")
_dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
_table = _dynamodb.Table(TABLE_NAME)


def _response(status: int, body):
    return {"statusCode": status, "body": json.dumps(body)}


def list_puzzles(event, context):
    """Return all coding puzzles from the DynamoDB table."""
    items = _table.scan().get("Items", [])
    return _response(200, items)


def add_puzzle(event, context):
    """Insert a new puzzle into the table."""
    data = json.loads(event.get("body", "{}"))
    if "id" not in data:
        data["id"] = str(uuid.uuid4())
    _table.put_item(Item=data)
    return _response(200, data)


def update_puzzle(event, context):
    """Replace an existing puzzle with new data."""
    data = json.loads(event.get("body", "{}"))
    if "id" not in data:
        return _response(400, {"error": "id required"})
    _table.put_item(Item=data)
    return _response(200, data)


def delete_puzzle(event, context):
    """Delete a puzzle by id."""
    puzzle_id = event.get("pathParameters", {}).get("id")
    if not puzzle_id:
        body = json.loads(event.get("body", "{}"))
        puzzle_id = body.get("id")
    if not puzzle_id:
        return _response(400, {"error": "id required"})
    _table.delete_item(Key={"id": puzzle_id})
    return _response(200, {"id": puzzle_id})
