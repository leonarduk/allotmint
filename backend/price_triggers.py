"""User-defined price triggers: "tell me when TICKER goes above/below PRICE".

A trigger belongs to one user (the resolved identity, as for alert thresholds)
and watches one ticker. Prices are GBP-normalised, matching the price
snapshot they are evaluated against.

``mode`` controls how often a trigger fires:

* ``once`` -- fires the first time the condition is met, then disables itself.
* ``continuous`` -- fires every time the price *crosses into* the condition
  (edge-triggered) and re-arms once the price is back on the other side. It
  does not fire on every price refresh while the condition stays met, which
  would flood the alert feed.

Persistence reuses the JSON storage abstraction (``file://``, ``s3://``,
``ssm://``) selected by ``PRICE_TRIGGERS_URI``. When that is unset and
``DATA_BUCKET`` is, triggers live in that bucket beside the other alert data
so Lambda deployments keep them across cold starts.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from backend.common.alerts import publish_alert
from backend.common.storage import JSONStorage, get_storage
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

CONDITIONS = ("above", "below")
MODES = ("once", "continuous")
MAX_TRIGGERS_PER_USER = 100

_S3_KEY = "alerts/price_triggers.json"
_UPDATABLE = ("ticker", "condition", "price", "mode", "enabled", "note")

_lock = threading.RLock()


class TriggerError(ValueError):
    """The request was invalid (bad field, unknown id, per-user limit)."""


class TriggerNotFound(TriggerError):
    """No trigger with the given id exists for that user."""


def _default_uri() -> str:
    explicit = os.getenv("PRICE_TRIGGERS_URI")
    if explicit:
        return explicit
    bucket = os.getenv("DATA_BUCKET")
    if bucket:
        return f"s3://{bucket}/{_S3_KEY}"
    root = config.repo_root or Path(__file__).resolve().parents[1]
    return f"file://{root / 'data' / 'price_triggers.json'}"


def _storage() -> JSONStorage:
    return get_storage(_default_uri())


def _load() -> Dict[str, Dict[str, Dict[str, Any]]]:
    data = _storage().load()
    return data if isinstance(data, dict) else {}


def _save(data: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    _storage().save(data)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _clean_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if not ticker:
        raise TriggerError("ticker is required")
    return ticker


def _clean_condition(value: Any) -> str:
    condition = str(value or "").strip().lower()
    if condition not in CONDITIONS:
        raise TriggerError(f"condition must be one of {', '.join(CONDITIONS)}")
    return condition


def _clean_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode not in MODES:
        raise TriggerError(f"mode must be one of {', '.join(MODES)}")
    return mode


def _clean_price(value: Any) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError) as exc:
        raise TriggerError("price must be a number") from exc
    if not math.isfinite(price) or price <= 0:
        raise TriggerError("price must be a positive number")
    return price


def _clean_note(value: Any) -> Optional[str]:
    note = str(value).strip() if value is not None else ""
    return note[:200] or None


def _clean_user(user: str) -> str:
    cleaned = (user or "").strip()
    if not cleaned:
        raise TriggerError("user is required")
    return cleaned


def _met(condition: str, price: float, target: float) -> bool:
    return price >= target if condition == "above" else price <= target


def list_triggers(user: str, ticker: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return ``user``'s triggers, oldest first, optionally for one ticker."""
    user = _clean_user(user)
    with _lock:
        rows = list(_load().get(user, {}).values())
    if ticker:
        wanted = _clean_ticker(ticker)
        rows = [r for r in rows if r["ticker"] == wanted]
    return sorted(rows, key=lambda r: r["created_at"])


def get_trigger(user: str, trigger_id: str) -> Dict[str, Any]:
    user = _clean_user(user)
    with _lock:
        row = _load().get(user, {}).get(trigger_id)
    if row is None:
        raise TriggerNotFound(f"price trigger {trigger_id!r} not found")
    return row


def create_trigger(
    user: str,
    *,
    ticker: Any,
    condition: Any,
    price: Any,
    mode: Any = "once",
    note: Any = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    user = _clean_user(user)
    row: Dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "ticker": _clean_ticker(ticker),
        "condition": _clean_condition(condition),
        "price": _clean_price(price),
        "mode": _clean_mode(mode),
        "enabled": bool(enabled),
        "note": _clean_note(note),
        "created_at": _now(),
        "last_triggered_at": None,
        "last_triggered_price": None,
        "trigger_count": 0,
        # Continuous triggers only fire on a fresh crossing; ``armed`` is
        # False while the condition is already met so it cannot fire again
        # until the price has moved back.
        "armed": True,
    }
    with _lock:
        data = _load()
        mine = data.setdefault(user, {})
        if len(mine) >= MAX_TRIGGERS_PER_USER:
            raise TriggerError(f"limit of {MAX_TRIGGERS_PER_USER} price triggers per user reached")
        mine[row["id"]] = row
        _save(data)
    return row


def update_trigger(user: str, trigger_id: str, **changes: Any) -> Dict[str, Any]:
    """Amend a trigger. Only fields in ``_UPDATABLE`` are accepted.

    Changing what a trigger watches (ticker, condition, price, mode) or
    re-enabling it re-arms it. A spent ``once`` trigger (one that fired and
    disabled itself) is also re-enabled by such an edit unless ``enabled`` is
    passed explicitly, since moving a fired alert almost always means setting
    a new one (#8588).
    """
    user = _clean_user(user)
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise TriggerError(f"cannot update: {', '.join(sorted(unknown))}")
    cleaners: Dict[str, Callable[[Any], Any]] = {
        "ticker": _clean_ticker,
        "condition": _clean_condition,
        "price": _clean_price,
        "mode": _clean_mode,
        "enabled": bool,
        "note": _clean_note,
    }
    with _lock:
        data = _load()
        row = data.get(user, {}).get(trigger_id)
        if row is None:
            raise TriggerNotFound(f"price trigger {trigger_id!r} not found")
        provided = {k: cleaners[k](v) for k, v in changes.items() if v is not None or k == "note"}
        if not provided:
            raise TriggerError("no fields to update")
        spent_once = row.get("mode") == "once" and not row.get("enabled") and bool(row.get("trigger_count"))
        row.update(provided)
        watch_changed = bool(provided.keys() & {"ticker", "condition", "price", "mode"})
        if watch_changed and spent_once and "enabled" not in provided:
            row["enabled"] = True
        if watch_changed or "enabled" in provided:
            row["armed"] = True
        _save(data)
    return row


def delete_trigger(user: str, trigger_id: str) -> Dict[str, Any]:
    user = _clean_user(user)
    with _lock:
        data = _load()
        row = data.get(user, {}).pop(trigger_id, None)
        if row is None:
            raise TriggerNotFound(f"price trigger {trigger_id!r} not found")
        if not data[user]:
            del data[user]
        _save(data)
    return row


def watched_tickers() -> List[str]:
    """Tickers with at least one enabled trigger, so the refresh can price them."""
    with _lock:
        data = _load()
    return sorted({r["ticker"] for rows in data.values() for r in rows.values() if r.get("enabled")})


def _message(row: Dict[str, Any], price: float) -> str:
    verb = "risen to or above" if row["condition"] == "above" else "fallen to or below"
    text = f"{row['ticker']} has {verb} £{row['price']:.2f} (now £{price:.2f})"
    return f"{text} - {row['note']}" if row.get("note") else text


def evaluate(prices: Mapping[str, Optional[float]]) -> List[Dict[str, Any]]:
    """Check every enabled trigger against ``prices`` (ticker -> GBP price).

    Fires alerts through :func:`backend.common.alerts.publish_alert` and
    persists the resulting state. Tickers with no usable price are skipped, so
    a failed price fetch neither fires nor re-arms anything. Returns the
    alerts fired.
    """
    quotes = {
        str(t).upper(): float(p)
        for t, p in prices.items()
        if isinstance(p, (int, float)) and math.isfinite(p) and p > 0
    }
    fired: List[Dict[str, Any]] = []
    with _lock:
        data = _load()
        changed = False
        for user, rows in data.items():
            for row in rows.values():
                price = quotes.get(row["ticker"])
                if price is None or not row.get("enabled"):
                    continue
                met = _met(row["condition"], price, row["price"])
                if not met:
                    if not row.get("armed", True):
                        row["armed"] = True
                        changed = True
                    continue
                if not row.get("armed", True):
                    continue
                row["armed"] = False
                row["last_triggered_at"] = _now()
                row["last_triggered_price"] = price
                row["trigger_count"] = int(row.get("trigger_count", 0)) + 1
                if row["mode"] == "once":
                    row["enabled"] = False
                changed = True
                fired.append(
                    {
                        "ticker": row["ticker"],
                        "user": user,
                        "trigger_id": row["id"],
                        "message": _message(row, price),
                    }
                )
        if changed:
            _save(data)
    for alert in fired:
        try:
            publish_alert(alert)
        except Exception as exc:  # one bad delivery must not drop the rest
            logger.error("Failed to publish price trigger alert: %s", sanitise_log_value(exc))
    return fired
