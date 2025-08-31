import backend.common.instrument_api as instrument_api


def test_update_latest_prices_from_snapshot_skips_none():
    instrument_api._LATEST_PRICES = {}
    snapshot = {
        "AAA.L": {"last_price": 123.45},
        "BBB.L": {"last_price": None},
        "CCC.L": {"other": 5},
        "DDD.L": None,
    }
    instrument_api.update_latest_prices_from_snapshot(snapshot)
    assert instrument_api._LATEST_PRICES == {"AAA.L": 123.45}
