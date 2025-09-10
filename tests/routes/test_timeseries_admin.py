import asyncio
import pandas as pd

from backend.routes import timeseries_admin
from backend.config import config



def test_summarize_fields(monkeypatch):
    monkeypatch.setattr(
        timeseries_admin,
        "get_instrument_meta",
        lambda *_args, **_kwargs: {"name": "Test"},
    )

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime([
                "2024-01-01",
                "2024-01-02",
                "2024-01-03",
            ]),
            "Source": ["A", "B", "A"],
        }
    )

    summary = timeseries_admin._summarize(df, "XYZ", "L")

    assert summary["earliest"] == "2024-01-01"
    assert summary["latest"] == "2024-01-03"
    assert summary["completeness"] == 100.0
    assert summary["main_source"] == "A"



def test_timeseries_admin_local(monkeypatch, tmp_path):
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime([
                "2024-01-01",
                "2024-01-02",
                "2024-01-03",
            ]),
            "Source": ["A", "B", "A"],
        }
    )

    meta_dir = tmp_path / "timeseries" / "meta"
    meta_dir.mkdir(parents=True)
    df.to_parquet(meta_dir / "ABC_L.parquet")

    monkeypatch.setattr(timeseries_admin, "get_instrument_meta", lambda *_: {"name": "Test"})
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)

    async def run():
        result = await timeseries_admin.timeseries_admin()
        assert result == [
            {
                "ticker": "ABC",
                "exchange": "L",
                "name": "Test",
                "earliest": "2024-01-01",
                "latest": "2024-01-03",
                "completeness": 100.0,
                "latest_source": "A",
                "main_source": "A",
            }
        ]

    asyncio.run(run())



def test_refetch_and_rebuild(monkeypatch, tmp_path):
    df = pd.DataFrame({"Date": pd.date_range("2024-01-01", periods=5)})

    def fake_load(t, e, days):
        assert t == "ABC"
        assert e == "L"
        return df

    monkeypatch.setattr(timeseries_admin, "load_meta_timeseries", fake_load)

    async def run():
        resp = await timeseries_admin.refetch_timeseries("abc", "l")
        assert resp == {"status": "ok", "rows": 5}

        cache_path = tmp_path / "cache.parquet"
        cache_path.write_text("x")

        def fake_cache_path(t, e):
            assert t == "ABC"
            assert e == "L"
            return cache_path

        monkeypatch.setattr(timeseries_admin, "meta_timeseries_cache_path", fake_cache_path)

        resp2 = await timeseries_admin.rebuild_cache("abc", "l")
        assert resp2 == {"status": "ok", "rows": 5}
        assert not cache_path.exists()

    asyncio.run(run())
