"""Contract tests for optional allotmint-pro feature handling."""

import pytest

from backend.common.core_optional import (
    UPGRADE_MESSAGE,
    CoreFeatureUnavailableError,
    missing_package,
    require_core,
)


def _missing_module(name: str) -> ModuleNotFoundError:
    return ModuleNotFoundError(f"No module named '{name}'", name=name)


@pytest.mark.parametrize("name", ["allotmint_pro", "allotmint_pro.risk"])
def test_missing_package_recognises_private_package_namespace(name: str) -> None:
    assert missing_package(_missing_module(name))


def test_missing_package_preserves_broken_private_install_errors() -> None:
    assert not missing_package(_missing_module("numpy"))


def test_require_core_returns_an_available_module() -> None:
    module = object()

    assert require_core(module, "Risk") is module


def test_require_core_explains_how_to_unlock_an_unavailable_feature() -> None:
    with pytest.raises(CoreFeatureUnavailableError) as raised:
        require_core(None, "Risk")

    assert raised.value.feature == "Risk"
    assert str(raised.value) == f"Risk is not available: {UPGRADE_MESSAGE}"
