from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field

SPA_RESPONSE_CONTRACT_VERSION = "2026-03-22"


class SpaContractBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfigTabsContract(SpaContractBase):
    portfolio: bool
    transactions: bool
    goals: bool
    tax: bool
    alerts: bool
    performance: bool
    wizard: bool
    ideas: bool
    reports: bool
    settings: bool
    queries: bool
    compliance: bool
    trade_compliance: bool = Field(alias="trade-compliance")
    pension: bool


class ConfigContract(SpaContractBase):
    app_env: str
    google_auth_enabled: bool | None = None
    google_client_id: str | None = None
    disable_auth: bool
    local_login_email: str | None = None
    theme: str | None = None
    relative_view_enabled: bool
    base_currency: str | None = None
    tabs: ConfigTabsContract
    disabled_tabs: List[str] = Field(default_factory=list)


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
    acquired_date: str
    currency: str | None = None
    price: float | None = None
    cost_basis_gbp: float | None = None
    cost_basis_currency: str | None = None
    effective_cost_basis_gbp: float | None = None
    effective_cost_basis_currency: str | None = None
    market_value_gbp: float | None = None
    market_value_currency: str | None = None
    gain_gbp: float | None = None
    gain_currency: float | None = None
    gain_pct: float | None = None
    current_price_gbp: float | None = None
    current_price_currency: float | None = None
    last_price_date: str | None = None
    last_price_time: str | None = None
    is_stale: bool | None = None
    latest_source: str | None = None
    day_change_gbp: float | None = None
    day_change_currency: float | None = None
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
    "ConfigContract",
    "OwnerSummaryContract",
    "GroupSummaryContract",
    "PortfolioContract",
    "TransactionContract",
    "ContractEnvelope",
]
