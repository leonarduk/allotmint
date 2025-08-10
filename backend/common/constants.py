from pathlib import Path

from backend.config import config

MAX_TRADES_PER_MONTH = config.max_trades_per_month
HOLD_DAYS_MIN = config.hold_days_min

_REPO_ROOT = Path(config.repo_root)
_PLOTS_ROOT = Path(config.accounts_root)
_PRICES_JSON = Path(config.prices_json)

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
