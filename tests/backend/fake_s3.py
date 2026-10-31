"""An in-memory S3 client for storage tests: get/put/list only, no network."""

from __future__ import annotations

import io
from typing import Optional

from botocore.exceptions import ClientError


class FakeS3:
    """Objects keyed by ``(bucket, key)``. ``fail_with`` makes every get_object raise that error code."""

    def __init__(self, fail_with: Optional[str] = None) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.fail_with = fail_with

    def get_object(self, Bucket, Key):  # noqa: N803
        if self.fail_with:
            raise ClientError({"Error": {"Code": self.fail_with, "Message": "x"}}, "GetObject")
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self.objects[(Bucket, Key)] = Body

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803
        keys = sorted(key for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix))
        # Two pages, so callers must not stop at the first one.
        half = len(keys) // 2
        return [{"Contents": [{"Key": k} for k in keys[:half]]}, {"Contents": [{"Key": k} for k in keys[half:]]}]
