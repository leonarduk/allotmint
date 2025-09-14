import logging

from backend.common import portfolio_utils


def test_get_security_meta_includes_sector_and_region():
    meta = portfolio_utils.get_security_meta("HFEL.L")
    assert meta is not None
    assert "sector" in meta and meta["sector"]
    assert "region" in meta and meta["region"]


def test_cash_meta_has_no_warning(caplog):
    caplog.set_level(logging.WARNING)
    meta = portfolio_utils._meta_from_file("CASH.GBP")
    assert meta and meta["asset_class"] == "cash"
    assert caplog.text == ""


def test_cash_alias_meta_has_no_warning(caplog):
    caplog.set_level(logging.WARNING)
    meta = portfolio_utils._meta_from_file("GBP.CASH")
    assert meta and meta["asset_class"] == "cash"
    assert caplog.text == ""
