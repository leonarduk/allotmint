import json
import sys
from datetime import datetime
import types

import pytest

import backend.common as _backend_common
from backend.common import portfolio_utils as pu


def test_portfolio_utils_import_does_not_call_load_snapshot(tmp_path, monkeypatch):
    """Importing portfolio_utils must not call _load_snapshot().

    A blocking S3 GetObject call at import time causes the Lambda init phase to
    exceed its 10 s limit, resulting in a cold-start 503.  Verified by pointing
    config.prices_json at a non-empty fixture file and confirming the module-level
    globals remain empty after a fresh import — if _load_snapshot() ran at import
    time, the sentinel ticker would appear in _PRICE_SNAPSHOT.
    """
    prices_file = tmp_path / "latest_prices.json"
    prices_file.write_text('{"SENTINEL.L": {"last_price": 1.0}}')

    monkeypatch.setattr(pu.config, "prices_json", prices_file, raising=False)
    monkeypatch.setattr(pu.config, "app_env", "local", raising=False)

    original_module = sys.modules.get("backend.common.portfolio_utils")
    sys.modules.pop("backend.common.portfolio_utils", None)
    try:
        import backend.common.portfolio_utils as fresh_pu  # noqa: PLC0415

        assert fresh_pu._PRICE_SNAPSHOT == {}, (
            "_load_snapshot() was called at import time; this triggers a blocking "
            "S3 call during Lambda init that exceeds the 10 s init limit (issue #2975)"
        )
        assert fresh_pu._PRICE_SNAPSHOT_TS is None
    finally:
        # Restore both sys.modules and the package attribute so that subsequent
        # monkeypatch.setattr("backend.common.portfolio_utils.*") calls land on
        # the same module object that route files imported at startup.  Without
        # restoring the package attribute, getattr(backend.common, "portfolio_utils")
        # returns the fresh reimport and the patch misses the live reference.
        sys.modules.pop("backend.common.portfolio_utils", None)
        if original_module is not None:
            sys.modules["backend.common.portfolio_utils"] = original_module
            _backend_common.portfolio_utils = original_module


def test_load_snapshot_missing_local_file(tmp_path, monkeypatch, caplog):
    path = tmp_path / "missing.json"
    monkeypatch.setattr(pu.config, "app_env", "local")
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)

    with caplog.at_level("WARNING"):
        data, ts = pu._load_snapshot()

    assert data == {}
    assert ts is None
    assert "Price snapshot not found" in caplog.text


def test_load_snapshot_aws_failure_falls_back_to_local(tmp_path, monkeypatch, caplog):
    payload = {"XYZ": {"price": 2}}
    path = tmp_path / "latest_prices.json"
    path.write_text(json.dumps(payload))

    class ClientError(Exception):
        pass

    class FakeS3:
        def get_object(self, Bucket, Key):  # noqa: N802
            raise ClientError("boom")

    fake_boto3 = types.SimpleNamespace(client=lambda service: FakeS3())
    fake_exc = types.SimpleNamespace(BotoCoreError=Exception, ClientError=ClientError)

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.setenv(pu.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exc)
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)

    with caplog.at_level("ERROR"):
        data, returned_ts = pu._load_snapshot()

    assert data == payload
    assert returned_ts == datetime.fromtimestamp(path.stat().st_mtime)
    assert "Failed to fetch price snapshot" in caplog.text


def _make_fake_s3_modules(fail: bool):
    """Return (fake_boto3, fake_botocore_exceptions) that raise or succeed."""

    class ClientError(Exception):
        pass

    if fail:

        class FakeS3:
            def get_object(self, Bucket, Key):  # noqa: N802
                raise ClientError("not found")

    else:

        class FakeS3:  # type: ignore[no-redef]
            def get_object(self, Bucket, Key):  # noqa: N802
                import io

                body = io.BytesIO(b'{"OK": {}}')
                return {"Body": body, "LastModified": None}

    fake_boto3 = types.SimpleNamespace(client=lambda service: FakeS3())
    fake_exc = types.SimpleNamespace(BotoCoreError=Exception, ClientError=ClientError)
    return fake_boto3, fake_exc


def test_load_snapshot_aws_s3_and_local_both_missing_logs_error(
    tmp_path, monkeypatch, caplog
):
    """ERROR (not WARNING) when S3 fails and local fallback file is also absent."""
    missing = tmp_path / "missing.json"
    fake_boto3, fake_exc = _make_fake_s3_modules(fail=True)

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.setenv(pu.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exc)
    monkeypatch.setattr(pu.config, "prices_json", missing)
    monkeypatch.setattr(pu, "_PRICES_PATH", missing)

    import logging

    with caplog.at_level(logging.ERROR):
        data, ts = pu._load_snapshot()

    assert data == {}
    assert ts is None
    assert "No price data available" in caplog.text
    assert "Portfolio prices will be unavailable" in caplog.text
    assert "Price snapshot not found" not in caplog.text


def test_load_snapshot_aws_s3_fails_no_local_path_configured_logs_error(
    monkeypatch, caplog
):
    """ERROR when S3 fails and prices_json is not configured at all."""
    fake_boto3, fake_exc = _make_fake_s3_modules(fail=True)

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.setenv(pu.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exc)
    monkeypatch.setattr(pu.config, "prices_json", None)
    monkeypatch.setattr(pu, "_PRICES_PATH", None)

    import logging

    with caplog.at_level(logging.ERROR):
        data, ts = pu._load_snapshot()

    assert data == {}
    assert ts is None
    assert "No price data available" in caplog.text
    assert "no local fallback configured" in caplog.text


def _make_no_such_key_s3_modules(tmp_path):
    """Return (fake_boto3, fake_botocore_exceptions) that raise NoSuchKey ClientError."""

    class ClientError(Exception):
        def __init__(self, msg):
            super().__init__(msg)
            self.response = {"Error": {"Code": "NoSuchKey", "Message": msg}}

    class FakeS3:
        def get_object(self, Bucket, Key):  # noqa: N802
            raise ClientError("The specified key does not exist.")

    fake_boto3 = types.SimpleNamespace(client=lambda service: FakeS3())
    fake_exc = types.SimpleNamespace(BotoCoreError=Exception, ClientError=ClientError)
    return fake_boto3, fake_exc


def test_load_snapshot_nosuchkey_logs_warning_not_error(tmp_path, monkeypatch, caplog):
    """NoSuchKey S3 error must log WARNING (not ERROR) — expected on first deploy."""
    missing = tmp_path / "missing.json"
    fake_boto3, fake_exc = _make_no_such_key_s3_modules(tmp_path)

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.setenv(pu.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exc)
    monkeypatch.setattr(pu.config, "prices_json", missing)
    monkeypatch.setattr(pu, "_PRICES_PATH", missing)

    import logging

    with caplog.at_level(logging.WARNING):
        data, ts = pu._load_snapshot()

    assert data == {}
    assert ts is None
    # Only one WARNING — no ERROR log
    assert "not yet present in S3" in caplog.text
    assert "not yet seeded" in caplog.text
    assert "Failed to fetch price snapshot" not in caplog.text
    assert "No price data available" not in caplog.text
    records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert records == [], f"Expected no ERROR logs for NoSuchKey; got: {[r.message for r in records]}"


def test_load_snapshot_nosuchkey_no_local_path_logs_single_warning(
    monkeypatch, caplog
):
    """NoSuchKey + no local path configured: single WARNING, no ERROR."""
    fake_boto3, fake_exc = _make_no_such_key_s3_modules(None)

    monkeypatch.setattr(pu.config, "app_env", "aws")
    monkeypatch.setenv(pu.DATA_BUCKET_ENV, "bucket")
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exc)
    monkeypatch.setattr(pu.config, "prices_json", None)
    monkeypatch.setattr(pu, "_PRICES_PATH", None)

    import logging

    with caplog.at_level(logging.WARNING):
        data, ts = pu._load_snapshot()

    assert data == {}
    assert ts is None
    warning_texts = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    error_texts = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_texts == [], f"Expected no ERROR logs for NoSuchKey; got: {error_texts}"
    assert any("not yet" in m for m in warning_texts), (
        f"Expected a 'not yet seeded' warning; got: {warning_texts}"
    )


def test_load_snapshot_non_aws_missing_local_logs_only_warning(
    tmp_path, monkeypatch, caplog
):
    """Non-AWS env: missing local file logs WARNING, not ERROR."""
    missing = tmp_path / "missing.json"

    monkeypatch.setattr(pu.config, "app_env", "local")
    monkeypatch.setattr(pu.config, "prices_json", missing)
    monkeypatch.setattr(pu, "_PRICES_PATH", missing)

    import logging

    with caplog.at_level(logging.WARNING):
        data, ts = pu._load_snapshot()

    assert data == {}
    assert ts is None
    assert "Price snapshot not found" in caplog.text
    assert "No price data available" not in caplog.text
