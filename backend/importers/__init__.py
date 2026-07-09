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
    "hargreaves": "backend.importers.hargreaves",
    "moneyhub": "backend.importers.moneyhub",
    "test": "backend.importers.test",
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


def dedupe_against_existing(candidates: List[Transaction], existing: List[Transaction]) -> List[Transaction]:
    """Filter ``candidates`` down to those not already present in ``existing``.

    Comparison is keyed on ``Transaction.external_id`` -- the source
    provider's own stable transaction id (e.g. Moneyhub's per-row ``Id``).
    ``Transaction.id`` cannot be used for this: it is a synthetic
    ``owner:account:index`` value regenerated positionally on every load (see
    ``_build_transaction_id`` in ``backend.routes.transactions``), so it never
    matches across a re-import of the same source row. Candidates without an
    ``external_id`` have no stable key to compare against and are always
    treated as new (this includes providers like ``degiro``/``hargreaves``
    that don't set ``external_id`` at all). Shared across import providers
    so this scheme isn't reimplemented per-provider -- see issue #3425,
    which independently needs the same dedupe behaviour for the live
    Moneyhub API importer.
    """
    existing_ids = {t.external_id for t in existing if t.external_id}
    return [t for t in candidates if not (t.external_id and t.external_id in existing_ids)]
