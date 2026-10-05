"""Per-instrument store of dividends and splits (#9340).

Cached ``timeseries/meta`` prices are the traded price: Yahoo is called with
``auto_adjust=False`` (see ``fetch_yahoo_timeseries``), so ``Close`` is never
re-based when a dividend is paid. Total return is derived from those prices
plus the dividends kept here (``backend.timeseries.total_return``), never
stored as ``Close``.

Layout, under the timeseries cache base (``<data root>/timeseries``)::

    corporate_actions/<SYMBOL>_<EXCHANGE>.parquet

one row per event, keyed on ``(Date, Action)``:

``Date``
    Ex-date (``datetime64[ms]``, no time zone).
``Action``
    ``dividend``, ``split`` or ``capital_gain``.
``Value``
    Dividend/capital gain: cash per share in the units of the price series
    (``Currency``); Yahoo reports them in the same units it quotes
    ``Close`` in, which is what makes price + dividend arithmetic valid.
    Split: shares after per share before (``2.0`` for a 2-for-1).
``Currency``
    Price currency reported by the provider (``GBP``, ``GBp``, ``USD``...),
    or empty when unknown.
``Source``
    Provider label, e.g. ``Yahoo``.

Rows are filled from the same Yahoo ``history`` call that fetches prices,
so no request path ever makes an extra network call for them. Writes merge
incrementally (fetched rows win per key) and are skipped when nothing
changes.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

ACTIONS_DIR = "corporate_actions"
ACTION_COLUMNS = ["Date", "Action", "Value", "Currency", "Source"]

# Ticker/exchange identifiers become a file name: allowlist them so a caller
# cannot steer the path outside ``corporate_actions/`` (``..``, separators).
_SAFE_IDENTIFIER_RE = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,19}")

DIVIDEND = "dividend"
SPLIT = "split"
CAPITAL_GAIN = "capital_gain"

# yfinance ``history(actions=True)`` column -> stored ``Action``.
_YAHOO_ACTION_COLUMNS = {
    "Dividends": DIVIDEND,
    "Stock Splits": SPLIT,
    "Capital Gains": CAPITAL_GAIN,
}


def empty_actions() -> pd.DataFrame:
    frame = pd.DataFrame({col: pd.Series(dtype="object") for col in ACTION_COLUMNS})
    frame["Date"] = pd.Series(dtype="datetime64[ms]")
    frame["Value"] = pd.Series(dtype="float64")
    return frame


def _naive_dates(values) -> pd.Series:
    dates = pd.to_datetime(pd.Series(values))
    if getattr(dates.dt, "tz", None) is not None:
        # Exchange-local midnight -> that calendar day; converting to UTC
        # first would move London summer dates back a day.
        dates = dates.dt.tz_localize(None)
    return dates.dt.normalize().astype("datetime64[ms]")


def actions_from_history(raw: pd.DataFrame, *, currency: str | None, source: str) -> pd.DataFrame:
    """Return the non-zero dividend/split/capital-gain events in a yfinance history frame."""
    if raw is None or raw.empty:
        return empty_actions()
    frame = raw.reset_index()
    date_col = "Date" if "Date" in frame.columns else frame.columns[0]
    parts = []
    for column, action in _YAHOO_ACTION_COLUMNS.items():
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        hits = values.notna() & (values != 0)
        if not hits.any():
            continue
        parts.append(
            pd.DataFrame(
                {
                    "Date": _naive_dates(frame.loc[hits, date_col]).to_numpy(),
                    "Action": action,
                    "Value": values[hits].astype(float).to_numpy(),
                    "Currency": currency or "",
                    "Source": source,
                }
            )
        )
    if not parts:
        return empty_actions()
    return _normalise(pd.concat(parts, ignore_index=True))


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.reindex(columns=ACTION_COLUMNS)
    frame["Date"] = _naive_dates(frame["Date"]).to_numpy()
    frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce").astype(float)
    frame["Action"] = frame["Action"].astype(str)
    frame["Currency"] = frame["Currency"].fillna("").astype(str)
    frame["Source"] = frame["Source"].fillna("").astype(str)
    frame = frame.loc[frame["Value"].notna()]
    frame = frame.drop_duplicates(subset=["Date", "Action"], keep="last")
    return frame.sort_values(["Date", "Action"]).reset_index(drop=True)


def _safe_identifier(value: str) -> str:
    cleaned = str(value).strip().upper()
    if not _SAFE_IDENTIFIER_RE.fullmatch(cleaned):
        raise ValueError(f"Unsafe ticker/exchange identifier: {sanitise_log_value(value)!r}")
    return cleaned


def _actions_root(base: str | None) -> str:
    """The store's directory: an ``s3://`` prefix, or a normalised local directory."""
    if base is None:
        # Lazy: ``cache`` imports the fetchers, which import this module.
        from backend.timeseries.cache import _cache_path

        root = _cache_path(ACTIONS_DIR)
    elif base.startswith("s3://"):
        root = "/".join([base.rstrip("/"), ACTIONS_DIR])
    else:
        root = str(Path(base, ACTIONS_DIR))
    return root.rstrip("/") if root.startswith("s3://") else os.path.normpath(root)


def _actions_filename(ticker: str, exchange: str) -> str:
    return f"{_safe_identifier(ticker)}_{_safe_identifier(exchange)}.parquet"


def corporate_actions_path(ticker: str, exchange: str, *, base: str | None = None) -> str:
    """Path of the actions file for ``ticker``/``exchange`` (same stem as its meta file).

    Raises ``ValueError`` for an identifier that is not a plain ticker/exchange code,
    or a local path that would escape the store directory.
    """
    root = _actions_root(base)
    name = _actions_filename(ticker, exchange)
    if root.startswith("s3://"):
        return f"{root}/{name}"
    path = os.path.normpath(os.path.join(root, name))
    if not path.startswith(root + os.sep):
        raise ValueError(f"Corporate actions path escapes {sanitise_log_value(root)!r}")
    return path


def load_corporate_actions(ticker: str, exchange: str, *, base: str | None = None) -> pd.DataFrame:
    """Stored events for ``ticker``/``exchange``; empty when none are stored."""
    actions = _read_actions(ticker, exchange, base=base)
    return empty_actions() if actions is None else actions


def _read_actions(ticker: str, exchange: str, *, base: str | None = None) -> pd.DataFrame | None:
    """Stored events, or ``None`` when there is no readable file (absent or unreadable)."""
    root = _actions_root(base)
    name = _actions_filename(ticker, exchange)
    if root.startswith("s3://"):
        path = f"{root}/{name}"
    else:
        # Normalise and confine in the same function as the read, so path-injection
        # analysis (CodeQL py/path-injection) sees the guard on the value it reads.
        path = os.path.normpath(os.path.join(root, name))
        if not path.startswith(root + os.sep):
            raise ValueError(f"Corporate actions path escapes {sanitise_log_value(root)!r}")
    try:
        frame = pd.read_parquet(path)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning(
            "Could not read corporate actions %s: %s",
            sanitise_log_value(path),
            sanitise_log_value(exc),
        )
        return None
    return _normalise(frame)


def load_dividends(ticker: str, exchange: str, *, base: str | None = None) -> pd.Series:
    """Cash dividend per share indexed by ex-date (summed when two share a date)."""
    actions = load_corporate_actions(ticker, exchange, base=base)
    return dividends_series(actions)


def stored_dividends(ticker: str, exchange: str, *, base: str | None = None) -> pd.Series | None:
    """Dividends for ``ticker``/``exchange``, or ``None`` when no actions file is stored.

    Unlike :func:`load_dividends`, this tells "no file" (dividend history
    unknown) apart from "a file with no dividends" (an empty series: none
    paid). Total-return consumers must not treat the first as the second.
    """
    actions = _read_actions(ticker, exchange, base=base)
    return None if actions is None else dividends_series(actions)


def dividends_series(actions: pd.DataFrame) -> pd.Series:
    rows = actions.loc[actions["Action"] == DIVIDEND]
    series = rows.groupby("Date")["Value"].sum()
    series.index.name = "Date"
    return series.astype(float)


def merge_actions(existing: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Merge ``new`` into ``existing`` by ``(Date, Action)``; return ``(merged, changed)``."""
    if new is None or new.empty:
        return existing, False
    new = _normalise(new)
    if existing.empty:
        return new, True
    existing = _normalise(existing)
    merged = _normalise(pd.concat([existing, new], ignore_index=True))
    if len(merged) != len(existing):
        return merged, True
    same_keys = (merged[["Date", "Action"]].to_numpy() == existing[["Date", "Action"]].to_numpy()).all()
    same_values = np.isclose(merged["Value"], existing["Value"], rtol=1e-9, atol=0.0).all()
    same_meta = (merged[["Currency", "Source"]].to_numpy() == existing[["Currency", "Source"]].to_numpy()).all()
    return merged, not (same_keys and same_values and same_meta)


def record_corporate_actions(
    ticker: str,
    exchange: str,
    actions: pd.DataFrame,
    *,
    base: str | None = None,
) -> bool:
    """Merge fetched ``actions`` into the store; return ``True`` when the file was written."""
    if actions is None or actions.empty:
        return False
    existing = load_corporate_actions(ticker, exchange, base=base)
    merged, changed = merge_actions(existing, actions)
    if not changed:
        return False
    root = _actions_root(base)
    name = _actions_filename(ticker, exchange)
    if root.startswith("s3://"):
        path = f"{root}/{name}"
    else:
        # Normalise and confine in the same function as the write (see load_corporate_actions).
        path = os.path.normpath(os.path.join(root, name))
        if not path.startswith(root + os.sep):
            raise ValueError(f"Corporate actions path escapes {sanitise_log_value(root)!r}")
        os.makedirs(root, exist_ok=True)
    merged.to_parquet(path, index=False)
    logger.info(
        "Stored %s corporate action(s) for %s.%s",
        sanitise_log_value(len(merged)),
        sanitise_log_value(ticker),
        sanitise_log_value(exchange),
    )
    return True
