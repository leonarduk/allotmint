from copy import deepcopy

import pytest

from backend.config import ConfigValidationError, TabsConfig, validate_config_data, validate_tabs


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


def test_validate_tabs_accepts_help():
    # Regression test for #7226: the frontend route registry's "help" page
    # (frontend/src/routes/registry.ts) has a `priority`, so it's picked up
    # by orderedTabPlugins and rendered as a toggle on the Support page's
    # Configuration tab. Saving that toggle must not fail with
    # "Unknown tab 'help'" -- see test_validate_tabs_accepts_all_frontend_tab_ids
    # below for the general regression guard this is a specific instance of.
    assert TabsConfig().help is True
    tabs = validate_tabs({"help": False})
    assert isinstance(tabs, TabsConfig)
    assert tabs.help is False


def test_validate_tabs_rejects_unknown_key():
    with pytest.raises(ConfigValidationError):
        validate_tabs({"unknown": True})


def test_validate_tabs_supports_trade_compliance_aliases():
    tabs = validate_tabs({"trade-compliance": False})
    assert tabs.trade_compliance is False

    legacy = validate_tabs({"tradecompliance": False})
    assert legacy.trade_compliance is False


def test_validate_config_data_rejects_unknown_tab():
    # validate_config_data() is what PUT /config runs *before* writing, so it
    # must apply the same validation load_config() would apply to the file.
    with pytest.raises(ConfigValidationError, match="not_a_real_tab"):
        validate_config_data({"ui": {"tabs": {"not_a_real_tab": True}}})


def test_validate_config_data_accepts_valid_document():
    cfg = validate_config_data({"ui": {"tabs": {"market": False}}})
    assert cfg.tabs.market is False
    assert cfg.tabs.instrument is True


def test_validate_config_data_does_not_mutate_input():
    # The caller writes the very dict it passes in, so validation must not
    # leave env overrides or normalisation artefacts behind in it.
    raw = {"ui": {"tabs": {"market": False}}, "auth": {"google_auth_enabled": False}}
    snapshot = deepcopy(raw)

    validate_config_data(raw)

    assert raw == snapshot


def test_validate_config_data_skips_google_auth_by_default(monkeypatch):
    # PUT /config does its own, deliberately more permissive Google-auth
    # handling; pre-validation must not reject a document over an environment
    # problem it already tolerates.
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "   ")

    cfg = validate_config_data({"auth": {"google_auth_enabled": True}})

    assert cfg.tabs.market is True

    with pytest.raises(ConfigValidationError):
        validate_config_data({"auth": {"google_auth_enabled": True}}, check_google_auth=True)


# The ids of every frontend route registry entry (frontend/src/routes/registry.ts)
# with `section: 'user'` or `section: 'support'` and a numeric `priority` -- i.e.
# every id `frontend/src/tabPlugins.ts`'s `orderedTabPlugins` exposes, which is
# what `Support.tsx`'s Configuration tab toggles and saves via `PUT /config`.
# This list must be kept in sync with registry.ts by hand: there's no shared
# schema between the TS registry and this Python dataclass, so a new frontend
# mode with a `priority` needs both a registry.ts entry AND a TabsConfig field.
#
# This is a *third* regression of the same class as #5871 (dataquality) and
# the "help" case above: `PUT /config` writes `ui.tabs` to config.yaml BEFORE
# `validate_tabs` runs (backend/routes/config.py), and `load_config()` runs
# at backend import time (backend/config.py) -- so an unknown tab key doesn't
# just 400 the save request, it corrupts config.yaml and the backend then
# fails to boot on every subsequent start (local/docker; Lambda's read-only
# config.yaml just 500s the write instead). See PR review on #7226.
_FRONTEND_TAB_IDS = [
    "group",
    "plot",
    "market",
    "movers",
    "instrument",
    "owner",
    "performance",
    "transactions",
    "trading",
    "screener",
    "timeseries",
    "watchlist",
    "allocation",
    "instrumentadmin",
    "rebalance",
    "dataadmin",
    "dataquality",
    "dataexplorer",
    "reports",
    "trail",
    "alertsettings",
    "settings",
    "pension",
    "taxtools",
    "trade-compliance",
    "support",
    "help",
    "scenario",
    "research",
]


def test_validate_tabs_accepts_all_frontend_tab_ids():
    tabs = validate_tabs({tab_id: False for tab_id in _FRONTEND_TAB_IDS})
    assert isinstance(tabs, TabsConfig)
    for tab_id in _FRONTEND_TAB_IDS:
        field_name = tab_id.replace("-", "_")
        assert getattr(tabs, field_name) is False, tab_id
