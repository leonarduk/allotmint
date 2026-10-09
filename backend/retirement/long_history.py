"""Long-history annual GBP returns (``timeseries/long_history/annual_returns_gbp.csv``).

The CSV lives in the data repo beside the timeseries cache, so it is resolved
through the same base as :mod:`backend.timeseries.cache` (a local path or an
``s3://`` URI). One row per calendar year; returns are nominal decimals in GBP.
A blank cell means the source has no data for that year: it is kept as
``None`` here and must never be read as a 0% return.
"""

from __future__ import annotations

import csv
import io
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

LONG_HISTORY_PARTS = ("long_history", "annual_returns_gbp.csv")
CPI_COLUMN = "uk_cpi_inflation"
#: Asset blocks with a return series (``gbp_per_usd`` is an FX level, not a return).
RETURN_BLOCKS: tuple[str, ...] = (
    "uk_cash",
    "uk_govt_bond_10y",
    "uk_equity",
    "us_equity_gbp",
    "ex_us_dev_equity_gbp",
    "us_small_value_gbp",
    "gold_gbp",
)
RETURN_BASIS = "total_return"


class LongHistoryError(RuntimeError):
    """The long-history CSV is missing or unreadable."""


@dataclass(frozen=True)
class LongHistory:
    """Per-year nominal block returns and UK CPI; missing cells are ``None``."""

    years: tuple[int, ...]
    cpi: dict[int, Optional[float]]
    blocks: dict[str, dict[int, Optional[float]]]
    source: str = ""
    basis: str = RETURN_BASIS
    notes: list[str] = field(default_factory=list)

    def value(self, block: str, year: int) -> Optional[float]:
        return self.blocks.get(block, {}).get(year)

    def coverage(self, column: str) -> Optional[tuple[int, int]]:
        """First and last year with a value for ``column`` (a block or the CPI column)."""
        series = self.cpi if column == CPI_COLUMN else self.blocks.get(column, {})
        present = [year for year, value in series.items() if value is not None]
        return (min(present), max(present)) if present else None


def _cell(raw: Optional[str]) -> Optional[float]:
    text = (raw or "").strip()
    if not text:
        return None
    value = float(text)
    return value if math.isfinite(value) else None


def parse_long_history(text: str, source: str = "") -> LongHistory:
    """Parse the CSV text. Blank cells become ``None``; a malformed number raises ``ValueError``."""
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    if "year" not in header or CPI_COLUMN not in header:
        raise ValueError(f"Long-history CSV needs 'year' and '{CPI_COLUMN}' columns")
    present_blocks = [block for block in RETURN_BLOCKS if block in header]
    cpi: dict[int, Optional[float]] = {}
    blocks: dict[str, dict[int, Optional[float]]] = {block: {} for block in present_blocks}
    for row in reader:
        year = int(str(row["year"]).strip())
        cpi[year] = _cell(row.get(CPI_COLUMN))
        for block in present_blocks:
            blocks[block][year] = _cell(row.get(block))
    years = tuple(sorted(cpi))
    if years and years != tuple(range(years[0], years[-1] + 1)):
        raise ValueError("Long-history CSV years must be consecutive with no gaps or duplicates")
    missing = [block for block in RETURN_BLOCKS if block not in header]
    notes = [f"Long-history CSV has no column for {', '.join(missing)}."] if missing else []
    return LongHistory(years=years, cpi=cpi, blocks=blocks, source=source, notes=notes)


def long_history_location() -> str:
    """Where the CSV is read from: ``{timeseries_cache_base}/long_history/annual_returns_gbp.csv``."""
    from backend.timeseries import cache as ts_cache

    return ts_cache._cache_path(*LONG_HISTORY_PARTS)


def _read_s3_text(uri: str) -> str:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    bucket, _, key = uri[len("s3://") :].partition("/")
    try:
        body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        raise LongHistoryError(f"Cannot read long-history CSV from S3: {exc}") from exc
    return body.decode("utf-8")


def read_location_text(location: str) -> str:
    """Text at a local path or ``s3://`` URI; raises :class:`LongHistoryError` if absent."""
    if location.startswith("s3://"):
        return _read_s3_text(location)
    try:
        return Path(location).read_text(encoding="utf-8")
    except OSError as exc:
        raise LongHistoryError(f"Long-history CSV not found at {location}") from exc


def load_long_history(location: Optional[str] = None) -> LongHistory:
    """Load and parse the long-history CSV from the data store (read-only)."""
    where = location or long_history_location()
    text = read_location_text(where)
    try:
        return parse_long_history(text, source=where)
    except (ValueError, KeyError) as exc:
        logger.warning("Unreadable long-history CSV %s: %s", sanitise_log_value(where), sanitise_log_value(exc))
        raise LongHistoryError(f"Long-history CSV at {where} is malformed: {exc}") from exc
