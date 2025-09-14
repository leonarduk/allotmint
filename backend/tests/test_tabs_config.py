import pytest

from backend.config import TabsConfig, validate_tabs, ConfigValidationError


def test_validate_tabs_accepts_new_keys():
    tabs = validate_tabs({
        "market": False,
        "allocation": True,
        "rebalance": False,
        "pension": True,
        "alertsettings": True,
    })
    assert isinstance(tabs, TabsConfig)
    assert tabs.market is False
    assert tabs.allocation is True
    assert tabs.rebalance is False
    assert tabs.pension is True
    assert tabs.alertsettings is True


def test_validate_tabs_rejects_unknown_key():
    with pytest.raises(ConfigValidationError):
        validate_tabs({"unknown": True})
