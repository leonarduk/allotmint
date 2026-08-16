"""Shared plumbing for features that live in the private ``allotmint-core``
package (screener, risk/VaR, compliance rule engine, allowances,
anomaly-repair).

Modules that re-export symbols from ``allotmint_core`` (e.g.
:mod:`backend.common.risk`) should catch ``ModuleNotFoundError`` at import
time and re-raise with :data:`UPGRADE_MESSAGE` so the failure is
self-explanatory wherever it surfaces (logs, tracebacks, tests).

Routes that need one of those modules at request time should import it inside
a ``try/except ModuleNotFoundError`` guard (setting a ``None`` sentinel on
failure — see :mod:`backend.reports` for the established pattern), then call
:func:`require_core` at the point of use so an unavailable feature reliably
turns into a 402 response instead of a 500.
"""

from __future__ import annotations

UPGRADE_MESSAGE = (
    "This feature requires the allotmint-core package, which is not installed "
    "in this deployment. See https://github.com/leonarduk/allotmint-core for "
    "upgrade options."
)


class CoreFeatureUnavailableError(RuntimeError):
    """Raised when a request needs an allotmint-core-only feature that isn't installed.

    Mapped to a 402 response by the handler registered in :func:`backend.app.create_app`.
    """

    def __init__(self, feature: str) -> None:
        super().__init__(f"{feature} is not available: {UPGRADE_MESSAGE}")
        self.feature = feature


def require_core(module: object | None, feature: str) -> object:
    """Return ``module`` unchanged, or raise :class:`CoreFeatureUnavailableError`.

    ``module`` is the sentinel set by a caller's
    ``try/except ModuleNotFoundError`` import guard: the imported module on
    success, ``None`` if allotmint-core isn't installed.
    """

    if module is None:
        raise CoreFeatureUnavailableError(feature)
    return module
