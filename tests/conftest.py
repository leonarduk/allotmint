import os
import pytest
import boto3
from moto import mock_aws

import backend.common.data_loader as dl

@pytest.fixture()
def s3_bucket(monkeypatch):
    """Create a temporary S3 bucket using moto and set DATA_BUCKET env."""
    with mock_aws():
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
        s3 = boto3.client("s3", region_name="us-east-1")
        bucket = "bucket"
        s3.create_bucket(Bucket=bucket)
        monkeypatch.setenv(dl.DATA_BUCKET_ENV, bucket)
        yield s3, bucket


@pytest.fixture()
def quotes_table(monkeypatch):
    """Provision a DynamoDB table for quote storage using moto."""
    with mock_aws():
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="Quotes",
            KeySchema=[{"AttributeName": "symbol", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "symbol", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield table
