from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field

SPA_RESPONSE_CONTRACT_VERSION = "2026-07-08"


class SpaContractBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AwsUiAuthContract(SpaContractBase):
    enabled: bool
    domain: str | None = None
    client_id: str | None = Field(default=None, alias="clientId")


class ConfigTabsContract(SpaContractBase):
    instrument: bool
    performance: bool
    transactions: bool
    screener: bool
    query: bool
    trading: bool
    timeseries: bool
    watchlist: bool
    movers: bool
    market: bool
    allocation: bool
    rebalance: bool
    instrumentadmin: bool
    group: bool
    owner: bool
    dataadmin: bool
    dataquality: bool
    dataexplorer: bool
    virtual: bool
    support: bool
    settings: bool
    alertsettings: bool
    trade_compliance: bool = Field(alias="trade-compliance")
    trail: bool
    taxtools: bool
    profile: bool
    pension: bool
    reports: bool
    scenario: bool
    logs: bool
    research: bool
    plot: bool
    help: bool


class ConfigContract(SpaContractBase):
    """Describes the subset of the real ``GET /config`` response the SPA relies on.

    ``serialise_config()`` also exposes internal/backend-only settings (API
    keys, rate limits, file paths, etc.) that the SPA never reads, so extra
    top-level fields are ignored here. ``tabs`` is still validated strictly
    via ``ConfigTabsContract`` since tab-name drift is what previously broke
    the SPA (see #5871).

    Fields deliberately left out of this contract (present on
    ``backend.config.Config`` but not validated/consumed here) include
    ``rate_limit_per_minute``, ``signup_rate_limit``, ``portfolio_xml_path``,
    ``transactions_output_root``, ``repo_root``, ``data_root``,
    ``accounts_root``, and similar file-path/limit settings -- none of these
    are secrets, so ``extra="ignore"`` is a reasonable relaxation for them.

    However, ``backend.config.Config`` *also* holds real secrets --
    ``telegram_bot_token``, ``alpha_vantage_key``, ``yahoo_news_key``,
    ``google_news_key`` -- and ``routes/config.py:read_config`` returns
    ``serialise_config()``'s full dict (typed ``Dict[str, Any]``, not this
    contract) directly as the HTTP response body, so these are not actually
    filtered out before reaching the client. ``extra="ignore"`` here only
    affects this test/contract-validation model; it does not redact the
    live API response. This is tracked for a dedicated fix rather than
    handled in this contract (see issue #5953).
    ``serialise_config()`` also exposes internal/backend-only settings (rate
    limits, file paths, etc.) that the SPA never reads, so extra top-level
    fields are ignored here. ``tabs`` is still validated strictly via
    ``ConfigTabsContract`` since tab-name drift is what previously broke the
    SPA (see #5871).

    NOTE: ``extra="ignore"`` here is a validation convenience, not a security
    boundary — it only relaxes what this *test-time* contract checks, it does
    not redact anything from the real HTTP response. Secrets (API keys,
    tokens, SNS ARNs) must never reach ``serialise_config()``'s return value
    in the first place; they are stripped explicitly in
    ``backend.routes.config._SECRET_CONFIG_FIELDS`` before this contract is
    ever applied (see #5953).
    """

    model_config = ConfigDict(extra="ignore")

    app_env: str
    google_auth_enabled: bool | None = None
    google_client_id: str | None = None
    disable_auth: bool
    local_login_email: str | None = None
    allowed_emails: List[str] | None = None
    theme: str | None = None
    relative_view_enabled: bool | None = None
    base_currency: str | None = None
    tabs: ConfigTabsContract
    disabled_tabs: List[str] = Field(default_factory=list)
    aws_ui_auth: AwsUiAuthContract | None = Field(default=None, alias="awsUiAuth")


class OwnerSummaryContract(SpaContractBase):
    owner: str
    full_name: str
    accounts: List[str]
    email: str | None = None
    has_transactions_artifact: bool = False


class GroupSummaryContract(SpaContractBase):
    slug: str
    name: str
    members: List[str] = Field(default_factory=list)


class HoldingContract(SpaContractBase):
    ticker: str
    name: str
    units: float
    # None when no real transaction/lot date is on record -- must stay
    # genuinely absent rather than a fabricated fallback date (#7220).
    acquired_date: str | None = None
    currency: str | None = None
    price: float | None = None
    cost_basis_gbp: float | None = None
    cost_basis_currency: str | None = None
    effective_cost_basis_gbp: float | None = None
    effective_cost_basis_currency: str | None = None
    market_value_gbp: float | None = None
    market_value_currency: str | None = None
    gain_gbp: float | None = None
    gain_currency: str | None = None  # currency code e.g. "GBP", not a numeric value
    gain_pct: float | None = None
    current_price_gbp: float | None = None
    current_price_currency: str | None = None  # currency code e.g. "GBP"
    last_price_date: str | None = None
    last_price_time: str | None = None
    is_stale: bool | None = None
    latest_source: str | None = None
    day_change_gbp: float | None = None
    day_change_currency: str | None = None  # currency code e.g. "GBP"
    instrument_type: str | None = None
    sector: str | None = None
    region: str | None = None
    forward_7d_change_pct: float | None = None
    forward_30d_change_pct: float | None = None
    days_held: int | None = None
    sell_eligible: bool | None = None
    days_until_eligible: int | None = None
    next_eligible_sell_date: str | None = None


class AccountContract(SpaContractBase):
    account_type: str
    currency: str
    last_updated: str | None = None
    value_estimate_gbp: float
    value_estimate_currency: str | None = None
    holdings: List[HoldingContract]
    owner: str | None = None


class PortfolioContract(SpaContractBase):
    owner: str
    as_of: str
    trades_this_month: int
    trades_remaining: int
    total_value_estimate_gbp: float
    total_value_estimate_currency: str | None = None
    accounts: List[AccountContract]


class TransactionContract(SpaContractBase):
    owner: str
    account: str
    id: str | None = None
    external_id: str | None = None
    date: str | None = None
    ticker: str | None = None
    type: str | None = None
    kind: str | None = None
    amount_minor: float | None = None
    currency: str | None = None
    security_ref: str | None = None
    price_gbp: float | None = None
    price: float | None = None
    shares: float | None = None
    units: float | None = None
    fees: float | None = None
    comments: str | None = None
    reason: str | None = None
    reason_to_buy: str | None = None
    synthetic: bool = False
    instrument_name: str | None = None


class ContractEnvelope(SpaContractBase):
    version: str = SPA_RESPONSE_CONTRACT_VERSION
    config: ConfigContract
    owners: List[OwnerSummaryContract]
    groups: List[GroupSummaryContract]
    portfolio: PortfolioContract
    transactions: List[TransactionContract]


__all__ = [
    "SPA_RESPONSE_CONTRACT_VERSION",
    "AwsUiAuthContract",
    "ConfigContract",
    "OwnerSummaryContract",
    "GroupSummaryContract",
    "PortfolioContract",
    "TransactionContract",
    "ContractEnvelope",
]
