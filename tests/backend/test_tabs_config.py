import pytest

from backend.config import ConfigValidationError, TabsConfig, validate_tabs


def test_validate_tabs_accepts_new_keys():
    tabs = validate_tabs({
        "market": False,
        "allocation": True,
        "rebalance": False,
        "pension": True,
        "alertsettings": True,
        "research": True,
    })
    assert isinstance(tabs, TabsConfig)
    assert tabs.market is False
    assert tabs.allocation is True
    assert tabs.rebalance is False
    assert tabs.pension is True
    assert tabs.alertsettings is True
    assert tabs.research is True


def test_validate_tabs_rejects_unknown_key():
    with pytest.raises(ConfigValidationError):
        validate_tabs({"unknown": True})


def test_validate_tabs_supports_trade_compliance_aliases():
    tabs = validate_tabs({"trade-compliance": False})
    assert tabs.trade_compliance is False

    legacy = validate_tabs({"tradecompliance": False})
    assert legacy.trade_compliance is False
