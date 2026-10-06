from pathlib import Path

from backend.config import config

MAX_TRADES_PER_MONTH = config.max_trades_per_month
HOLD_DAYS_MIN = config.hold_days_min

_REPO_ROOT = Path(config.repo_root) if config.repo_root else None
_PLOTS_ROOT = Path(config.accounts_root) if config.accounts_root else None
_PRICES_JSON = Path(config.prices_json) if config.prices_json else None

UNITS = "units"

ACCOUNTS = "accounts"

OWNER = "owner"

TICKER = "ticker"

HOLDINGS = "holdings"

MARKET_VALUE_GBP = "market_value_gbp"

EFFECTIVE_COST_BASIS_GBP = "effective_cost_basis_gbp"

COST_BASIS_GBP = "cost_basis_gbp"

ACQUIRED_DATE = "acquired_date"

GAIN_GBP = "gain_gbp"

GAIN_PCT = "gain_pct"

DAYS_HELD = "days_held"


# Trailing price-change windows exposed on instrument rows: field -> days back.
PRICE_CHANGE_WINDOWS = {
    "change_7d_pct": 7,
    "change_30d_pct": 30,
    "change_90d_pct": 90,
    "change_1y_pct": 365,
}
