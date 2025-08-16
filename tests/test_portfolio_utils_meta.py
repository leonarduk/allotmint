from backend.common import portfolio_utils


def test_get_security_meta_includes_sector_and_region():
    meta = portfolio_utils.get_security_meta("HFEL.L")
    assert meta is not None
    assert "sector" in meta and meta["sector"]
    assert "region" in meta and meta["region"]

