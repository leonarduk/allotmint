"""Provider specific transaction importers."""

from __future__ import annotations

from importlib import import_module
from typing import Dict, List, Callable, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.routes.transactions import Transaction


class UnknownProvider(Exception):
    """Raised when no importer exists for the requested provider."""

    pass


_IMPORTER_PATHS: Dict[str, str] = {
    "degiro": "backend.importers.degiro",
}


def parse(provider: str, data: bytes) -> List[Transaction]:
    """Parse raw file ``data`` from ``provider`` into transactions.

    Parameters
    ----------
    provider:
        Name of the provider, e.g. ``"degiro"``.
    data:
        Raw file contents.
    """
    module_path = _IMPORTER_PATHS.get(provider.lower())
    if not module_path:
        raise UnknownProvider(provider)
    module: Callable[[bytes], List[Transaction]] = import_module(module_path)
    return module.parse(data)  # type: ignore[attr-defined]
