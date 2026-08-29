import re
from copy import deepcopy
from dataclasses import fields
from pathlib import Path

import pytest

from backend.config import ConfigValidationError, TabsConfig, validate_config_data, validate_tabs

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_TS_PATH = REPO_ROOT / "frontend" / "src" / "routes" / "registry.ts"

_ARRAY_RE = re.compile(
    r"export const ROUTE_REGISTRY: RouteRegistryEntry\[\] = \[(.*?)\n\];",
    re.DOTALL,
)
_MODE_RE = re.compile(r"mode:\s*'([^']+)'")
_SECTION_RE = re.compile(r"section:\s*'([^']+)'")
_PRIORITY_RE = re.compile(r"priority:\s*(-?\d+)")


def _frontend_tab_ids() -> list[str]:
    """Derive, by parsing registry.ts, the ids of every ROUTE_REGISTRY entry
    with `section: 'user'` or `section: 'support'` and a numeric `priority`
    -- i.e. every id frontend/src/tabPlugins.ts's `orderedTabPlugins`
    exposes, which is what Support.tsx's Configuration tab toggles and
    saves via `PUT /config`.

    This mirrors orderedTabPlugins' own filter:
        (page.section === 'user' || page.section === 'support') &&
        typeof page.priority === 'number'
    but is implemented independently in Python (regex over the .ts source,
    like tests/test_styles_snapshot.py already does for index.css) so that
    it is a real regression guard and not a second, hand-maintained copy of
    the same list that can silently go stale. A hand-maintained list is
    exactly how #5871 (dataquality) and the "help" case above both slipped
    through: it's accurate the day it's written and wrong the day someone
    adds a mode to registry.ts without touching this file.
    """
    source = REGISTRY_TS_PATH.read_text(encoding="utf-8")
    array_match = _ARRAY_RE.search(source)
    if not array_match:
        raise AssertionError(
            f"Could not locate 'export const ROUTE_REGISTRY: RouteRegistryEntry[] = [' "
            f"...'];' in {REGISTRY_TS_PATH}. The parser regex is stale (the array was "
            "renamed/reformatted) -- fix _ARRAY_RE, don't let this test pass on an "
            "empty/partial match."
        )
    body = array_match.group(1)

    # Split into individual object entries on the '  {' that opens each one
    # at the array's own indentation level (two spaces). This only breaks on
    # object boundaries, not on nested braces/strings within a value.
    blocks = re.split(r"\n  \{\n", body)[1:]

    ids: list[str] = []
    for block in blocks:
        mode_match = _MODE_RE.search(block)
        section_match = _SECTION_RE.search(block)
        priority_match = _PRIORITY_RE.search(block)
        if not (mode_match and section_match and priority_match):
            continue
        if section_match.group(1) not in ("user", "support"):
            continue
        ids.append(mode_match.group(1))

    return ids


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


def test_validate_tabs_accepts_all_frontend_tab_ids():
    # This is a *third* regression of the same class as #5871 (dataquality)
    # and the "help" case above: `PUT /config` writes `ui.tabs` to
    # config.yaml BEFORE `validate_tabs` runs (backend/routes/config.py),
    # and `load_config()` runs at backend import time (backend/config.py) --
    # so an unknown tab key doesn't just 400 the save request, it corrupts
    # config.yaml and the backend then fails to boot on every subsequent
    # start (local/docker; Lambda's read-only config.yaml just 500s the
    # write instead). See PR review on #7226.
    #
    # `_frontend_tab_ids()` parses registry.ts directly rather than
    # comparing against a hand-maintained list here, specifically so a
    # *future* addition to registry.ts is caught even if nobody remembers to
    # touch this file -- a hand-maintained list is accurate the day it's
    # written and is exactly the failure mode this test exists to catch.
    tab_ids = _frontend_tab_ids()

    # Fail loudly if the parser found nothing (or an implausibly small set):
    # a silently-empty/partial match would make every assertion below pass
    # vacuously, which is worse than no test at all.
    assert len(tab_ids) >= 20, (
        f"Only parsed {len(tab_ids)} tab id(s) from {REGISTRY_TS_PATH}; the "
        "registry has ~30 user/support entries with a priority, so this "
        "almost certainly means the parser broke (registry.ts's format "
        "changed) rather than the registry actually shrinking this much. "
        "Fix _frontend_tab_ids()/its regexes before trusting this test again."
    )

    known_fields = {f.name for f in fields(TabsConfig)}
    expected_fields = {tab_id.replace("-", "_") for tab_id in tab_ids}
    missing = expected_fields - known_fields
    assert missing == set(), (
        f"backend.config.TabsConfig has no field for frontend tab id(s): "
        f"{sorted(missing)}. Add them to TabsConfig (backend/config.py) and "
        "ConfigTabsContract (backend/contracts_spa.py), or PUT /config will "
        "400 with \"Unknown tab '...'\" and corrupt config.yaml on the way."
    )

    # Also exercise the real validation path end-to-end, not just field
    # presence, mirroring exactly what Support.tsx's Configuration tab sends.
    tabs = validate_tabs({tab_id: False for tab_id in tab_ids})
    assert isinstance(tabs, TabsConfig)
    for tab_id in tab_ids:
        field_name = tab_id.replace("-", "_")
        assert getattr(tabs, field_name) is False, tab_id
