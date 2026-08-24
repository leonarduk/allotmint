import pytest

from backend.config import ConfigValidationError, TabsConfig, validate_tabs


def test_validate_tabs_accepts_new_keys():
    tabs = validate_tabs(
        {
            "market": False,
            "allocation": True,
            "rebalance": False,
            "pension": True,
            "alertsettings": True,
            "research": True,
        }
    )
    assert isinstance(tabs, TabsConfig)
    assert tabs.market is False
    assert tabs.allocation is True
    assert tabs.rebalance is False
    assert tabs.pension is True
    assert tabs.alertsettings is True
    assert tabs.research is True


def test_validate_tabs_accepts_dataquality():
    # Regression test for #5871: the Support page's frontend route registry
    # includes a "dataquality" tab (data-quality page) that must have a
    # matching TabsConfig field, or saving the Support page's tab toggles
    # fails with "Unknown tab 'dataquality'".
    tabs = validate_tabs({"dataquality": False})
    assert isinstance(tabs, TabsConfig)
    assert tabs.dataquality is False


def test_validate_tabs_accepts_plot():
    # Plot mode (the gamified skin at /plot) is a normal config tab, so the
    # Support page's tab toggles must be able to save it like any other.
    assert TabsConfig().plot is True
    tabs = validate_tabs({"plot": False})
    assert isinstance(tabs, TabsConfig)
    assert tabs.plot is False


def test_validate_tabs_rejects_unknown_key():
    with pytest.raises(ConfigValidationError):
        validate_tabs({"unknown": True})


def test_validate_tabs_supports_trade_compliance_aliases():
    tabs = validate_tabs({"trade-compliance": False})
    assert tabs.trade_compliance is False

    legacy = validate_tabs({"tradecompliance": False})
    assert legacy.trade_compliance is False
