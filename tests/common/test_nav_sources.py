"""Where CsvNavProvider finds navs.csv: S3 first, then data_root, then the bundled copy.

S3 is a stub client (no AWS calls), following tests/test_alerts_storage.py.
"""

from __future__ import annotations

import io
from datetime import date

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from backend.common import nav
from backend.common.nav import NAV_S3_KEY, CsvNavProvider, load_nav_csv_s3

HEADER = "ticker,nav,currency,nav_date,source\n"
S3_ROW = "3IN.L,380.5,GBX,2026-09-30,RNS\n"
LOCAL_ROW = "3IN.L,370.0,GBX,2026-08-31,local\n"


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "GetObject")


class StubS3:
    def __init__(self, body: str | None = None, error: Exception | None = None):
        self.body = body
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def get_object(self, Bucket, Key):
        self.calls.append((Bucket, Key))
        if self.error is not None:
            raise self.error
        return {"Body": io.BytesIO(self.body.encode("utf-8"))}


@pytest.fixture
def local_csv(tmp_path):
    path = tmp_path / "navs.csv"
    path.write_text(HEADER + LOCAL_ROW, encoding="utf-8")
    return path


def _provider(monkeypatch, s3, paths, bucket="data-bucket"):
    monkeypatch.setattr(nav, "_s3_client", lambda: s3)
    return CsvNavProvider(lambda: paths, bucket_factory=lambda: bucket)


def test_reads_the_bucket_copy_when_a_bucket_is_configured(monkeypatch, local_csv):
    s3 = StubS3(body=HEADER + S3_ROW)
    provider = _provider(monkeypatch, s3, (local_csv,))

    record = provider.latest_nav("3in.l")

    assert record.nav == 380.5 and record.nav_date == date(2026, 9, 30)
    assert s3.calls == [("data-bucket", NAV_S3_KEY)]


def test_bucket_reads_are_cached(monkeypatch, local_csv):
    s3 = StubS3(body=HEADER + S3_ROW)
    provider = _provider(monkeypatch, s3, (local_csv,))

    provider.latest_nav("3IN.L")
    provider.latest_nav("3IN.L")

    assert len(s3.calls) == 1


def test_missing_bucket_object_falls_back_to_the_local_file(monkeypatch, local_csv):
    s3 = StubS3(error=_client_error("NoSuchKey"))
    provider = _provider(monkeypatch, s3, (local_csv,))

    assert provider.latest_nav("3IN.L").source == "local"


@pytest.mark.parametrize("error", [_client_error("AccessDenied"), EndpointConnectionError(endpoint_url="https://s3")])
def test_s3_failure_is_logged_and_falls_back(monkeypatch, local_csv, caplog, error):
    s3 = StubS3(error=error)
    provider = _provider(monkeypatch, s3, (local_csv,))

    assert provider.latest_nav("3IN.L").source == "local"
    assert "using the local NAV file" in caplog.text


def test_no_bucket_means_no_s3_call(monkeypatch, local_csv):
    def no_client():
        raise AssertionError("S3 must not be used without DATA_BUCKET")

    monkeypatch.setattr(nav, "_s3_client", no_client)
    provider = CsvNavProvider(lambda: (local_csv,), bucket_factory=lambda: None)

    assert provider.latest_nav("3IN.L").source == "local"


def test_first_existing_local_path_wins(tmp_path, local_csv):
    # Lambda: data_root (/tmp/data) is empty, so the bundled copy is read.
    empty_data_root = tmp_path / "tmp-data" / "nav" / "navs.csv"
    provider = CsvNavProvider(lambda: (empty_data_root, local_csv), bucket_factory=lambda: None)

    assert provider.latest_nav("3IN.L").source == "local"


def test_no_file_anywhere_gives_no_nav(tmp_path):
    provider = CsvNavProvider(lambda: (tmp_path / "a.csv", tmp_path / "b.csv"), bucket_factory=lambda: None)
    assert provider.latest_nav("3IN.L") is None


def test_load_nav_csv_s3_returns_none_only_for_a_missing_object(monkeypatch):
    monkeypatch.setattr(nav, "_s3_client", lambda: StubS3(error=_client_error("NoSuchKey")))
    assert load_nav_csv_s3("data-bucket") is None

    monkeypatch.setattr(nav, "_s3_client", lambda: StubS3(error=_client_error("AccessDenied")))
    with pytest.raises(ClientError):
        load_nav_csv_s3("data-bucket")


def test_default_sources_are_data_bucket_then_data_root_then_bundled(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_BUCKET", "env-bucket")
    monkeypatch.setattr(nav.config, "data_root", tmp_path)

    assert nav._default_bucket() == "env-bucket"
    data_root_csv, bundled_csv = nav._default_csv_paths()
    assert data_root_csv == tmp_path / "nav" / "navs.csv"
    assert bundled_csv.parts[-3:] == ("data", "nav", "navs.csv")
    assert bundled_csv.parent.parent.parent == nav.Path(nav.__file__).resolve().parents[2]
