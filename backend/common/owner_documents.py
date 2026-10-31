"""One JSON document per owner, on local disk or in S3 (#11159).

Investment plans and the decision journal each keep ``<owner>.json`` under one
base. Locally the base is a directory under ``data_root`` (the private data
repo). On AWS ``data_root`` is the Lambda's empty, per-container ``/tmp/data``
(``config.lambda.yaml``), so an environment variable such as ``PLANS_URI``
names an ``s3://<bucket>/<prefix>`` base instead, the same way
``PLAN_BRIEFS_URI`` does for saved briefs (``backend/plan_brief/store.py``).

Owner ids are validated by the callers before they reach this module.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from backend.common.path_utils import safe_join
from backend.common.storage import S3JSONStorage, list_s3_json_stems


@dataclass(frozen=True)
class OwnerDocumentStore:
    """Where ``<owner>.json`` documents live: ``$<uri_env>`` when it is an ``s3://`` URI, else ``local_dir``."""

    uri_env: str
    local_dir: Callable[[Optional[Path]], Path]

    def _s3_base(self) -> Optional[tuple[str, str]]:
        uri = os.getenv(self.uri_env, "").strip()
        if not uri:
            return None
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise ValueError(f"{self.uri_env} must be an s3://bucket/prefix URI, got {uri!r}")
        return parsed.netloc, parsed.path.strip("/")

    def _s3(self, owner: str) -> Optional[S3JSONStorage]:
        base = self._s3_base()
        if base is None:
            return None
        bucket, prefix = base
        return S3JSONStorage(bucket=bucket, key=f"{prefix}/{owner}.json" if prefix else f"{owner}.json")

    def local_path(self, owner: str, data_root: Optional[Path]) -> Path:
        return safe_join(self.local_dir(data_root), f"{owner}.json")

    def read(self, owner: str, data_root: Optional[Path]) -> Optional[Any]:
        """The parsed document, or ``None`` when none is stored. Read errors raise."""
        storage = self._s3(owner)
        if storage is not None:
            return storage.load_existing()
        try:
            return json.loads(self.local_path(owner, data_root).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def write(self, owner: str, data: dict[str, Any], data_root: Optional[Path]) -> Optional[Path]:
        """Store ``data``; returns the local path, or ``None`` when it went to S3.

        The local write is atomic (temp file and rename) and pretty-printed, so
        diffs in the data repo stay readable.
        """
        storage = self._s3(owner)
        if storage is not None:
            storage.save(data)
            return None
        path = self.local_path(owner, data_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{owner}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return path

    def owners(self, data_root: Optional[Path] = None) -> set[str]:
        """Owners with a stored document. Listing errors raise."""
        base = self._s3_base()
        if base is not None:
            return set(list_s3_json_stems(*base))
        directory = self.local_dir(data_root)
        return {path.stem for path in directory.glob("*.json")} if directory.is_dir() else set()
