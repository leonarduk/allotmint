"""Every config key the Configuration page lists has a description (#9645).

``Support.tsx`` renders each key of ``GET /config`` (``serialise_config``)
except ``tabs`` and ``mcp_tools``, which have their own sections, and looks
up ``support.config.descriptions.<key>`` with an empty fallback. A key
without an entry silently shows no description, so a typo or a newly added
``Config`` field would go unnoticed without this check.
"""

import json
from pathlib import Path

import pytest

from backend.config import Config
from backend.routes.config import _SECRET_CONFIG_FIELDS, serialise_config

LOCALES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales"
# Rendered by dedicated sections of the page, not the generic parameter list.
_OWN_SECTION_KEYS = {"tabs", "mcp_tools"}


def _listed_keys() -> set[str]:
    return set(serialise_config(Config())) - _OWN_SECTION_KEYS


def _descriptions(locale: Path) -> dict[str, str]:
    data = json.loads((locale / "translation.json").read_text(encoding="utf-8"))
    return data["support"]["config"]["descriptions"]


@pytest.mark.parametrize("locale", sorted(LOCALES.iterdir()), ids=lambda p: p.name)
def test_every_listed_config_key_has_a_description(locale: Path) -> None:
    descriptions = _descriptions(locale)
    missing = sorted(key for key in _listed_keys() if not str(descriptions.get(key) or "").strip())
    assert not missing, f"{locale.name}: no support.config.descriptions entry for {missing}"


def test_descriptions_name_only_listed_config_keys() -> None:
    # Catches a typo'd description key (e.g. snapshot_warm_day), which would
    # otherwise leave both the typo and the real key undocumented.
    stale = sorted(set(_descriptions(LOCALES / "en")) - _listed_keys())
    assert not stale, f"descriptions for keys GET /config does not list: {stale}"


def test_secret_fields_are_neither_listed_nor_described() -> None:
    descriptions = _descriptions(LOCALES / "en")
    assert not set(_SECRET_CONFIG_FIELDS) & (_listed_keys() | set(descriptions))
