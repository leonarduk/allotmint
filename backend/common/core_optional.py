"""Shared plumbing for features that live in the private ``allotmint-pro``
package (screener, risk/VaR, compliance rule engine, allowances,
anomaly-repair).

Modules that re-export symbols from ``allotmint_pro`` (e.g.
:mod:`backend.common.risk`) should catch ``ModuleNotFoundError`` at import
time and re-raise with :data:`UPGRADE_MESSAGE` so the failure is
self-explanatory wherever it surfaces (logs, tracebacks, tests). Use
:func:`missing_package` to check ``exc.name`` first — ``allotmint_pro`` being
installed but missing one of *its own* dependencies (e.g. numpy) also raises
``ModuleNotFoundError``, and that should surface as the real broken-install
error, not get mislabelled as "not installed".

Routes that need one of those modules at request time should import it inside
a ``try/except ModuleNotFoundError`` guard (setting a ``None`` sentinel on
failure — see :mod:`backend.reports` for the established pattern), then call
:func:`require_core` at the point of use so an unavailable feature reliably
turns into a 402 response instead of a 500.
"""

from __future__ import annotations

UPGRADE_MESSAGE = (
    "This feature requires the allotmint-pro package, which is not installed "
    "in this deployment. See https://github.com/leonarduk/allotmint-pro for "
    "upgrade options."
)


def missing_package(exc: ModuleNotFoundError, package: str = "allotmint_pro") -> bool:
    """Return whether ``exc`` was raised because ``package`` itself is absent.

    ``exc.name`` is the dotted name of the module that Python actually
    failed to find — for ``from allotmint_pro.risk import x`` that's
    ``"allotmint_pro"`` (or ``"allotmint_pro.risk"``) when the package isn't
    installed, but it's some third-party name like ``"numpy"`` when
    ``allotmint_pro`` is installed and merely missing one of its own
    dependencies. Callers should only rewrite the error message when this
    returns ``True``; otherwise re-raise the original exception unchanged.
    """

    name = exc.name or ""
    return name == package or name.startswith(f"{package}.")


class CoreFeatureUnavailableError(RuntimeError):
    """Raised when a request needs an allotmint-pro-only feature that isn't installed.

    Mapped to a 402 response by the handler registered in :func:`backend.app.create_app`.
    """

    def __init__(self, feature: str) -> None:
        super().__init__(f"{feature} is not available: {UPGRADE_MESSAGE}")
        self.feature = feature


def require_core(module: object | None, feature: str) -> object:
    """Return ``module`` unchanged, or raise :class:`CoreFeatureUnavailableError`.

    ``module`` is the sentinel set by a caller's
    ``try/except ModuleNotFoundError`` import guard: the imported module on
    success, ``None`` if allotmint-pro isn't installed.
    """

    if module is None:
        raise CoreFeatureUnavailableError(feature)
    return module
