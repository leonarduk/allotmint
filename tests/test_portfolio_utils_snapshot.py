from backend.common import portfolio_utils as pu


def test_load_snapshot_bad_json(tmp_path, monkeypatch, caplog):
    path = tmp_path / "latest_prices.json"
    path.write_text("{bad json")
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)
    with caplog.at_level("ERROR"):
        data, ts = pu._load_snapshot()
    assert data == {}
    assert ts is None
    assert "Failed to parse snapshot" in caplog.text


def test_load_snapshot_no_path(monkeypatch, caplog):
    monkeypatch.setattr(pu.config, "prices_json", None)
    monkeypatch.setattr(pu, "_PRICES_PATH", None)
    with caplog.at_level("INFO"):
        data, ts = pu._load_snapshot()
    assert data == {}
    assert ts is None
    assert "Price snapshot path not configured; skipping load" in caplog.text
