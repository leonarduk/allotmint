from pathlib import Path

MAX_TRADES_PER_MONTH = 20
HOLD_DAYS_MIN        = 30

_REPO_ROOT   = Path(__file__).resolve().parents[2]
_PLOTS_ROOT  = _REPO_ROOT / "data" / "accounts"
_PRICES_JSON = _REPO_ROOT / "data" / "prices" / "latest_prices.json"

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
