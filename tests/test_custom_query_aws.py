import io
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app import create_app
import backend.routes.query as qr


BASE_QUERY = {
    "start": "2025-01-01",
    "end": "2025-01-10",
    "tickers": ["HFEL.L"],
    "metrics": ["var", "meta"],
}


def test_s3_save_load_and_list(monkeypatch):
    monkeypatch.setattr(qr.config, "app_env", "aws", raising=False)
    monkeypatch.setenv(qr.DATA_BUCKET_ENV, "bucket")

    storage: dict[str, bytes] = {}

    def fake_client(name):
        assert name == "s3"

        def put_object(Bucket, Key, Body):
            assert Bucket == "bucket"
            storage[Key] = Body

        def get_object(Bucket, Key):
            assert Bucket == "bucket"
            if Key not in storage:
                raise KeyError
            return {"Body": io.BytesIO(storage[Key])}

        def list_objects_v2(**kwargs):
            assert kwargs["Bucket"] == "bucket"
            assert kwargs["Prefix"] == qr.QUERIES_PREFIX
            return {"Contents": [{"Key": k} for k in storage.keys()]}

        return SimpleNamespace(
            put_object=put_object, get_object=get_object, list_objects_v2=list_objects_v2
        )

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    client = TestClient(create_app())

    slug = "aws-query"
    resp = client.post(f"/custom-query/{slug}", json=BASE_QUERY)
    assert resp.status_code == 200

    resp = client.get(f"/custom-query/{slug}")
    assert resp.status_code == 200
    assert resp.json()["tickers"] == BASE_QUERY["tickers"]

    resp = client.get("/custom-query/saved")
    assert slug in resp.json()

