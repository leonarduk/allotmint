"""SigV4 request signing for calling an IAM-authenticated Lambda Function URL."""

from __future__ import annotations

from typing import Generator, Optional

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


class LambdaFunctionUrlSigV4Auth(httpx.Auth):
    """Signs outgoing requests for an ``AWS_IAM``-authenticated Lambda Function URL.

    Function URLs are signed as the ``lambda`` service, not ``execute-api``
    (API Gateway's service name) -- signing with the wrong service name
    produces a signature AWS silently rejects with 403, not a diagnosable
    error. Uses the process's normal credential chain (the Lambda execution
    role when running in AWS), the same way ``boto3.client("s3")`` already
    does elsewhere in ``backend/common/*`` -- no new credential handling.
    """

    def __init__(self, region: Optional[str] = None) -> None:
        session = boto3.Session()
        credentials = session.get_credentials()
        if credentials is None:
            raise RuntimeError("No AWS credentials available to sign requests")
        self._credentials = credentials
        self._region = region or session.region_name
        if not self._region:
            raise RuntimeError("No AWS region resolved to sign requests (set AWS_REGION/AWS_DEFAULT_REGION)")

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers=dict(request.headers),
        )
        SigV4Auth(self._credentials, "lambda", self._region).add_auth(aws_request)
        request.headers.update(dict(aws_request.headers))
        yield request
