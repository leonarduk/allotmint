"""
AWS Lambda handler for AllotMint production API Gateway integration.

Expected Lambda proxy integration event with pathParameters:
  owner
  account
"""

import json
import os

from backend.common.data_loader import load_account


def handler(event, context):  # AWS Lambda signature
    os.environ.setdefault("ALLOTMINT_ENV", "aws")
    try:
        owner = event["pathParameters"]["owner"]
        account = event["pathParameters"]["account"]
        data = load_account(owner, account)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(data),
        }
    except KeyError:
        return {"statusCode": 400, "body": json.dumps({"error": "Missing path parameters"})}
    except FileNotFoundError:
        return {"statusCode": 404, "body": json.dumps({"error": "Not found"})}
    except Exception as exc:  # noqa: BLE001
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}
