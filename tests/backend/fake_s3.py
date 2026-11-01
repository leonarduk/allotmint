"""An in-memory S3 client for storage tests: get/put/list only, no network."""

from __future__ import annotations

import io
from typing import Optional

import botocore.session
from botocore.exceptions import ClientError
from botocore.paginate import Paginator


class FakeS3:
    """Objects keyed by ``(bucket, key)``. ``fail_with`` makes every get_object raise that error code.

    ``page_size`` switches listing to S3's truncation contract: ``list_objects_v2``
    returns at most that many keys with ``IsTruncated``/``NextContinuationToken``,
    and ``get_paginator`` hands back botocore's real paginator over it, so only a
    caller that follows the continuation token sees every key (#11176).
    ``omit_continuation_token`` drops the token from truncated pages (a malformed
    response). Without ``page_size`` the paginator is a fixed two-page split.
    """

    def __init__(
        self,
        fail_with: Optional[str] = None,
        page_size: Optional[int] = None,
        omit_continuation_token: bool = False,
    ) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.fail_with = fail_with
        self.page_size = page_size
        self.omit_continuation_token = omit_continuation_token
        self.list_calls: list[dict] = []

    def get_object(self, Bucket, Key):  # noqa: N803
        if self.fail_with:
            raise ClientError({"Error": {"Code": self.fail_with, "Message": "x"}}, "GetObject")
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self.objects[(Bucket, Key)] = Body

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None, **_):  # noqa: N803
        assert self.page_size is not None, "list_objects_v2 paging needs page_size"
        self.list_calls.append({"Prefix": Prefix, "ContinuationToken": ContinuationToken})
        keys = sorted(key for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix))
        start = int(ContinuationToken or 0)
        end = start + self.page_size
        page = {"Contents": [{"Key": k} for k in keys[start:end]], "IsTruncated": end < len(keys)}
        if page["IsTruncated"] and not self.omit_continuation_token:
            page["NextContinuationToken"] = str(end)
        return page

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        if self.page_size is None:
            return self
        session = botocore.session.get_session()
        config = session.get_paginator_model("s3").get_paginator("ListObjectsV2")
        model = session.get_service_model("s3").operation_model("ListObjectsV2")
        return Paginator(self.list_objects_v2, config, model)

    def paginate(self, Bucket, Prefix):  # noqa: N803
        keys = sorted(key for bucket, key in self.objects if bucket == Bucket and key.startswith(Prefix))
        # Two pages, so callers must not stop at the first one.
        half = len(keys) // 2
        return [{"Contents": [{"Key": k} for k in keys[:half]]}, {"Contents": [{"Key": k} for k in keys[half:]]}]
