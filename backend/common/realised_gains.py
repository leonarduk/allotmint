"""Realised gain/loss per disposal using UK Section 104 average-cost pooling.

The pooling itself lives in :mod:`backend.common.holdings_rebuild`, so realised
gains use the same date ordering as the cost basis written to
``<account>.json`` (acquisitions before disposals on the same day, undated rows
last), the same settled values, and the same matching of ticker-less trades to
tickers by instrument name.  The rebuild also learns a name's ticker from the
existing ``<account>.json`` holdings; a caller that passes those holdings as
``old_holdings`` (``GET /transactions`` does) keys a ticker-less trade whose
ticker appears only there identically to the rebuild (#8122).

A SELL's realised gain is ``proceeds - cost``, where ``cost`` is taken out of
the pool pro rata.  Units that entered the pool without a known cost (e.g. a
``TRANSFER_IN`` for a position held before the records begin) make any
disposal drawing on them indeterminate: ``realised_gain_gbp`` is ``None`` and
``unmatched_units`` reports how many of the units sold had no known cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from backend.common.holdings_rebuild import Disposal, name_aliases, replay_transactions

_EPS = 1e-9


@dataclass(frozen=True)
class DisposalGain:
    """Result for a single disposal transaction."""

    cost_basis_gbp: float
    proceeds_gbp: float | None
    realised_gain_gbp: float | None
    unmatched_units: float


def compute_disposal_gains(
    transactions: Sequence[Mapping[str, Any]],
    old_holdings: Sequence[Any] | None = None,
) -> dict[int, DisposalGain]:
    """Return realised gain results keyed by index into ``transactions``.

    ``transactions`` must all belong to one ``(owner, account)``.  Only
    disposals of a known instrument and quantity appear in the result;
    ``TRANSFER_OUT``/``REMOVAL`` reduce the pool without realising a gain.
    ``old_holdings`` is that account's current ``<account>.json`` holdings
    list, the same alias source ``rebuild_holdings_document`` uses.
    """
    rows = [tx for tx in transactions if isinstance(tx, Mapping)]
    known = [h for h in old_holdings or () if isinstance(h, Mapping)]
    positions = [i for i, tx in enumerate(transactions) if isinstance(tx, Mapping)]
    results: dict[int, DisposalGain] = {}

    def record(disposal: Disposal) -> None:
        if disposal.tx_type != "SELL":
            return
        unmatched = disposal.unknown_cost_units + disposal.unmatched_units
        proceeds = disposal.proceeds_gbp
        gain = None
        if proceeds is not None and unmatched <= _EPS:
            gain = round(proceeds - disposal.cost_gbp, 2)
        results[positions[disposal.index]] = DisposalGain(
            cost_basis_gbp=round(disposal.cost_gbp, 2),
            proceeds_gbp=None if proceeds is None else round(proceeds, 2),
            realised_gain_gbp=gain,
            unmatched_units=round(unmatched, 6) if unmatched > _EPS else 0.0,
        )

    # Only the per-disposal callback is needed; positions and cash are the rebuild's concern.
    _ = replay_transactions(rows, aliases=name_aliases(rows, known), on_disposal=record, warn=False)
    return results
