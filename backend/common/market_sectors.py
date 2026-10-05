"""Regional sector performance and per-sector drill-down for Market Overview.

Each region maps the 11 GICS sectors to a proxy instrument and a short list
of representative constituents:

* ``global`` - iShares Global sector ETFs (IXN, IXG, ...).
* ``us`` - SPDR Select Sector ETFs (XLK, XLF, ...).
* ``uk`` - no liquid UK sector-ETF family exists, so sector moves are the
  equal-weighted average of a hand-picked FTSE 100 basket.

Constituent lists are representative large holdings, not full index
membership; the UI labels them as such. Changes are percentages in each
instrument's own currency, so mixing listings (e.g. ``ASML`` and ``SHEL.L``)
in one basket is safe.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, List, Literal, Optional, Sequence, Tuple, TypedDict

import pandas as pd

from backend.logging_setup import sanitise_log_value
from backend.utils.lazy_import import lazy_import

yf = lazy_import("yfinance")

logger = logging.getLogger(__name__)

Region = Literal["global", "us", "uk"]
REGIONS: Tuple[Region, ...] = ("global", "us", "uk")
REGION_LABELS: Dict[Region, str] = {"global": "Global", "us": "US", "uk": "UK"}

# Rows of trading-day history returned for the detail chart (~3 months).
HISTORY_POINTS = 63


class SectorDefinition(TypedDict):
    proxy: Optional[Tuple[str, str]]
    constituents: List[Tuple[str, str]]


SECTOR_UNIVERSE: Dict[Region, Dict[str, SectorDefinition]] = {
    "global": {
        "Technology": {
            "proxy": ("IXN", "iShares Global Tech ETF"),
            "constituents": [
                ("AAPL", "Apple"),
                ("MSFT", "Microsoft"),
                ("NVDA", "NVIDIA"),
                ("TSM", "Taiwan Semiconductor"),
                ("ASML", "ASML Holding"),
            ],
        },
        "Health Care": {
            "proxy": ("IXJ", "iShares Global Healthcare ETF"),
            "constituents": [
                ("LLY", "Eli Lilly"),
                ("UNH", "UnitedHealth"),
                ("NVO", "Novo Nordisk"),
                ("ROG.SW", "Roche"),
                ("AZN.L", "AstraZeneca"),
            ],
        },
        "Financials": {
            "proxy": ("IXG", "iShares Global Financials ETF"),
            "constituents": [
                ("JPM", "JPMorgan Chase"),
                ("BRK-B", "Berkshire Hathaway"),
                ("V", "Visa"),
                ("HSBA.L", "HSBC"),
                ("8306.T", "Mitsubishi UFJ"),
            ],
        },
        "Energy": {
            "proxy": ("IXC", "iShares Global Energy ETF"),
            "constituents": [
                ("XOM", "Exxon Mobil"),
                ("CVX", "Chevron"),
                ("SHEL.L", "Shell"),
                ("TTE.PA", "TotalEnergies"),
                ("BP.L", "BP"),
            ],
        },
        "Consumer Discretionary": {
            "proxy": ("RXI", "iShares Global Consumer Discretionary ETF"),
            "constituents": [
                ("AMZN", "Amazon"),
                ("TSLA", "Tesla"),
                ("HD", "Home Depot"),
                ("7203.T", "Toyota"),
                ("MC.PA", "LVMH"),
            ],
        },
        "Consumer Staples": {
            "proxy": ("KXI", "iShares Global Consumer Staples ETF"),
            "constituents": [
                ("WMT", "Walmart"),
                ("PG", "Procter & Gamble"),
                ("COST", "Costco"),
                ("NESN.SW", "Nestle"),
                ("ULVR.L", "Unilever"),
            ],
        },
        "Industrials": {
            "proxy": ("EXI", "iShares Global Industrials ETF"),
            "constituents": [
                ("GE", "GE Aerospace"),
                ("CAT", "Caterpillar"),
                ("RTX", "RTX"),
                ("SIE.DE", "Siemens"),
                ("RR.L", "Rolls-Royce"),
            ],
        },
        "Materials": {
            "proxy": ("MXI", "iShares Global Materials ETF"),
            "constituents": [
                ("LIN", "Linde"),
                ("BHP", "BHP Group"),
                ("RIO.L", "Rio Tinto"),
                ("SHW", "Sherwin-Williams"),
                ("AI.PA", "Air Liquide"),
            ],
        },
        "Utilities": {
            "proxy": ("JXI", "iShares Global Utilities ETF"),
            "constituents": [
                ("NEE", "NextEra Energy"),
                ("SO", "Southern Company"),
                ("DUK", "Duke Energy"),
                ("IBE.MC", "Iberdrola"),
                ("NG.L", "National Grid"),
            ],
        },
        "Communication Services": {
            "proxy": ("IXP", "iShares Global Comm Services ETF"),
            "constituents": [
                ("GOOGL", "Alphabet"),
                ("META", "Meta Platforms"),
                ("NFLX", "Netflix"),
                ("0700.HK", "Tencent"),
                ("TMUS", "T-Mobile US"),
            ],
        },
        "Real Estate": {
            "proxy": ("REET", "iShares Global REIT ETF"),
            "constituents": [
                ("PLD", "Prologis"),
                ("AMT", "American Tower"),
                ("EQIX", "Equinix"),
                ("WELL", "Welltower"),
                ("SGRO.L", "Segro"),
            ],
        },
    },
    "us": {
        "Technology": {
            "proxy": ("XLK", "Technology Select Sector SPDR"),
            "constituents": [
                ("AAPL", "Apple"),
                ("MSFT", "Microsoft"),
                ("NVDA", "NVIDIA"),
                ("AVGO", "Broadcom"),
                ("ORCL", "Oracle"),
            ],
        },
        "Health Care": {
            "proxy": ("XLV", "Health Care Select Sector SPDR"),
            "constituents": [
                ("LLY", "Eli Lilly"),
                ("UNH", "UnitedHealth"),
                ("JNJ", "Johnson & Johnson"),
                ("ABBV", "AbbVie"),
                ("MRK", "Merck"),
            ],
        },
        "Financials": {
            "proxy": ("XLF", "Financial Select Sector SPDR"),
            "constituents": [
                ("BRK-B", "Berkshire Hathaway"),
                ("JPM", "JPMorgan Chase"),
                ("V", "Visa"),
                ("MA", "Mastercard"),
                ("BAC", "Bank of America"),
            ],
        },
        "Energy": {
            "proxy": ("XLE", "Energy Select Sector SPDR"),
            "constituents": [
                ("XOM", "Exxon Mobil"),
                ("CVX", "Chevron"),
                ("COP", "ConocoPhillips"),
                ("EOG", "EOG Resources"),
                ("SLB", "SLB"),
            ],
        },
        "Consumer Discretionary": {
            "proxy": ("XLY", "Consumer Discretionary Select Sector SPDR"),
            "constituents": [
                ("AMZN", "Amazon"),
                ("TSLA", "Tesla"),
                ("HD", "Home Depot"),
                ("MCD", "McDonald's"),
                ("BKNG", "Booking Holdings"),
            ],
        },
        "Consumer Staples": {
            "proxy": ("XLP", "Consumer Staples Select Sector SPDR"),
            "constituents": [
                ("WMT", "Walmart"),
                ("COST", "Costco"),
                ("PG", "Procter & Gamble"),
                ("KO", "Coca-Cola"),
                ("PEP", "PepsiCo"),
            ],
        },
        "Industrials": {
            "proxy": ("XLI", "Industrial Select Sector SPDR"),
            "constituents": [
                ("GE", "GE Aerospace"),
                ("CAT", "Caterpillar"),
                ("RTX", "RTX"),
                ("UBER", "Uber"),
                ("HON", "Honeywell"),
            ],
        },
        "Materials": {
            "proxy": ("XLB", "Materials Select Sector SPDR"),
            "constituents": [
                ("LIN", "Linde"),
                ("SHW", "Sherwin-Williams"),
                ("APD", "Air Products"),
                ("ECL", "Ecolab"),
                ("FCX", "Freeport-McMoRan"),
            ],
        },
        "Utilities": {
            "proxy": ("XLU", "Utilities Select Sector SPDR"),
            "constituents": [
                ("NEE", "NextEra Energy"),
                ("SO", "Southern Company"),
                ("DUK", "Duke Energy"),
                ("CEG", "Constellation Energy"),
                ("VST", "Vistra"),
            ],
        },
        "Communication Services": {
            "proxy": ("XLC", "Communication Services Select Sector SPDR"),
            "constituents": [
                ("META", "Meta Platforms"),
                ("GOOGL", "Alphabet"),
                ("NFLX", "Netflix"),
                ("DIS", "Walt Disney"),
                ("TMUS", "T-Mobile US"),
            ],
        },
        "Real Estate": {
            "proxy": ("XLRE", "Real Estate Select Sector SPDR"),
            "constituents": [
                ("PLD", "Prologis"),
                ("AMT", "American Tower"),
                ("EQIX", "Equinix"),
                ("WELL", "Welltower"),
                ("SPG", "Simon Property"),
            ],
        },
    },
    "uk": {
        "Technology": {
            "proxy": None,
            "constituents": [("SGE.L", "Sage Group"), ("HLMA.L", "Halma")],
        },
        "Health Care": {
            "proxy": None,
            "constituents": [
                ("AZN.L", "AstraZeneca"),
                ("GSK.L", "GSK"),
                ("HIK.L", "Hikma"),
                ("SN.L", "Smith & Nephew"),
            ],
        },
        "Financials": {
            "proxy": None,
            "constituents": [
                ("HSBA.L", "HSBC"),
                ("BARC.L", "Barclays"),
                ("LLOY.L", "Lloyds Banking"),
                ("NWG.L", "NatWest"),
                ("LSEG.L", "London Stock Exchange Group"),
                ("PRU.L", "Prudential"),
            ],
        },
        "Energy": {
            "proxy": None,
            "constituents": [("SHEL.L", "Shell"), ("BP.L", "BP")],
        },
        "Consumer Discretionary": {
            "proxy": None,
            "constituents": [
                ("CPG.L", "Compass Group"),
                ("NXT.L", "Next"),
                ("IHG.L", "InterContinental Hotels"),
                ("KGF.L", "Kingfisher"),
            ],
        },
        "Consumer Staples": {
            "proxy": None,
            "constituents": [
                ("ULVR.L", "Unilever"),
                ("DGE.L", "Diageo"),
                ("BATS.L", "British American Tobacco"),
                ("TSCO.L", "Tesco"),
                ("RKT.L", "Reckitt"),
            ],
        },
        "Industrials": {
            "proxy": None,
            "constituents": [
                ("RR.L", "Rolls-Royce"),
                ("BA.L", "BAE Systems"),
                ("REL.L", "RELX"),
                ("EXPN.L", "Experian"),
                ("AHT.L", "Ashtead"),
            ],
        },
        "Materials": {
            "proxy": None,
            "constituents": [
                ("RIO.L", "Rio Tinto"),
                ("GLEN.L", "Glencore"),
                ("AAL.L", "Anglo American"),
                ("ANTO.L", "Antofagasta"),
            ],
        },
        "Utilities": {
            "proxy": None,
            "constituents": [
                ("NG.L", "National Grid"),
                ("SSE.L", "SSE"),
                ("UU.L", "United Utilities"),
                ("SVT.L", "Severn Trent"),
            ],
        },
        "Communication Services": {
            "proxy": None,
            "constituents": [
                ("VOD.L", "Vodafone"),
                ("BT-A.L", "BT Group"),
                ("AUTO.L", "Auto Trader"),
                ("WPP.L", "WPP"),
            ],
        },
        "Real Estate": {
            "proxy": None,
            "constituents": [
                ("LAND.L", "Land Securities"),
                ("SGRO.L", "Segro"),
                ("BLND.L", "British Land"),
            ],
        },
    },
}


class RegionSector(TypedDict):
    sector: str
    change: float
    source: Literal["etf", "basket"]


class ConstituentQuote(TypedDict):
    ticker: str
    name: str
    price: Optional[float]
    change: Optional[float]


class HistoryPoint(TypedDict):
    date: str
    value: float


class SectorDetail(TypedDict):
    region: Region
    sector: str
    basis: Literal["etf", "basket"]
    proxy: Optional[Dict[str, str]]
    returns: Dict[str, Optional[float]]
    history: List[HistoryPoint]
    constituents: List[ConstituentQuote]


def normalise_region(value: Optional[str]) -> Optional[Region]:
    """Return the canonical region key for ``value`` or ``None`` if unknown."""

    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    return key if key in REGIONS else None  # type: ignore[return-value]


def find_sector(region: Region, name: str) -> Optional[str]:
    """Return the registry's spelling of ``name`` (case-insensitive) in ``region``."""

    wanted = name.strip().lower()
    for sector in SECTOR_UNIVERSE[region]:
        if sector.lower() == wanted:
            return sector
    return None


def _download_closes(symbols: Sequence[str], period: str) -> pd.DataFrame:
    """Return a ``date x ticker`` frame of daily closes (empty on no data)."""

    frame = yf.download(list(symbols), period=period, interval="1d", progress=False, auto_adjust=False)
    closes = frame.get("Close") if hasattr(frame, "get") else None
    if closes is None:
        return pd.DataFrame()
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=symbols[0])
    return closes


def _series(closes: pd.DataFrame, symbol: str) -> pd.Series:
    if symbol not in closes:
        return pd.Series(dtype=float)
    return pd.to_numeric(closes[symbol], errors="coerce").dropna()


def _pct_change(latest: float, base: float) -> Optional[float]:
    if base == 0:
        return None
    return (latest - base) / base * 100.0


def _day_change(series: pd.Series) -> Optional[float]:
    if len(series) < 2:
        return None
    return _pct_change(float(series.iloc[-1]), float(series.iloc[-2]))


def _basket_change(closes: pd.DataFrame, symbols: Sequence[str]) -> Optional[float]:
    changes = [c for c in (_day_change(_series(closes, s)) for s in symbols) if c is not None]
    if not changes:
        return None
    return sum(changes) / len(changes)


def fetch_region_sectors(region: Region) -> List[RegionSector]:
    """Return today's % change per sector for ``region``.

    ETF-backed regions use the proxy ETF's last two closes; basket regions use
    the equal-weighted mean of each constituent's day change. Sectors with no
    usable data are omitted and logged.
    """

    universe = SECTOR_UNIVERSE[region]
    symbols = sorted(
        {d["proxy"][0] for d in universe.values() if d["proxy"]}
        | {t for d in universe.values() if not d["proxy"] for t, _ in d["constituents"]}
    )
    closes = _download_closes(symbols, period="5d")

    out: List[RegionSector] = []
    for sector, definition in universe.items():
        if definition["proxy"]:
            change = _day_change(_series(closes, definition["proxy"][0]))
            source: Literal["etf", "basket"] = "etf"
        else:
            change = _basket_change(closes, [t for t, _ in definition["constituents"]])
            source = "basket"
        if change is None:
            logger.warning(
                "No sector change for %s/%s: close data missing",
                sanitise_log_value(region),
                sanitise_log_value(sector),
            )
            continue
        out.append({"sector": sector, "change": change, "source": source})
    return out


def _close_on_or_before(series: pd.Series, cutoff: pd.Timestamp) -> Optional[float]:
    window = series[series.index <= cutoff]
    return float(window.iloc[-1]) if not window.empty else None


def _period_returns(series: pd.Series) -> Dict[str, Optional[float]]:
    returns: Dict[str, Optional[float]] = {"1D": None, "1W": None, "1M": None, "YTD": None}
    if series.empty:
        return returns
    latest = float(series.iloc[-1])
    last_date = pd.Timestamp(series.index[-1])
    returns["1D"] = _day_change(series)
    cutoffs = {
        "1W": last_date - timedelta(days=7),
        "1M": last_date - timedelta(days=30),
        "YTD": pd.Timestamp(date(last_date.year - 1, 12, 31)),
    }
    for key, cutoff in cutoffs.items():
        base = _close_on_or_before(series, cutoff)
        if base is not None:
            returns[key] = _pct_change(latest, base)
    return returns


def _basket_index(closes: pd.DataFrame, symbols: Sequence[str]) -> pd.Series:
    """Equal-weighted index of ``symbols`` rebased to 100 at its first date.

    Each constituent is forward-filled across other exchanges' holidays and
    rebased on its own first close, so mixed listings line up. Constituents
    with no data at all are dropped first, so one dead ticker can't blank the
    whole index.
    """

    columns = [s for s in symbols if s in closes]
    if not columns:
        return pd.Series(dtype=float)
    numeric = closes[columns].apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    frame = numeric.ffill().dropna(how="any")
    if frame.empty:
        return pd.Series(dtype=float)
    rebased = frame.divide(frame.iloc[0]).multiply(100.0)
    return rebased.mean(axis=1)


def fetch_sector_detail(region: Region, sector: str) -> SectorDetail:
    """Return returns, recent history and constituent quotes for one sector.

    ``sector`` must already be the registry spelling (see ``find_sector``).
    """

    definition = SECTOR_UNIVERSE[region][sector]
    constituents = definition["constituents"]
    proxy = definition["proxy"]
    symbols = [t for t, _ in constituents] + ([proxy[0]] if proxy else [])
    closes = _download_closes(symbols, period="1y")

    if proxy:
        headline = _series(closes, proxy[0])
    else:
        headline = _basket_index(closes, [t for t, _ in constituents])

    quotes: List[ConstituentQuote] = []
    for ticker, name in constituents:
        series = _series(closes, ticker)
        quotes.append(
            {
                "ticker": ticker,
                "name": name,
                "price": float(series.iloc[-1]) if not series.empty else None,
                "change": _day_change(series),
            }
        )

    recent = headline.tail(HISTORY_POINTS)
    dates = pd.DatetimeIndex(recent.index).strftime("%Y-%m-%d")
    history: List[HistoryPoint] = [
        {"date": day, "value": float(val)} for day, val in zip(dates, recent.to_numpy(), strict=True)
    ]
    return {
        "region": region,
        "sector": sector,
        "basis": "etf" if proxy else "basket",
        "proxy": {"ticker": proxy[0], "name": proxy[1]} if proxy else None,
        "returns": _period_returns(headline),
        "history": history,
        "constituents": quotes,
    }
