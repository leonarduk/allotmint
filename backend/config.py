from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, overload

import os
import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TabsConfig:
    group: bool = False
    owner: bool = False
    instrument: bool = False
    performance: bool = False
    transactions: bool = False
    screener: bool = False
    query: bool = False
    trading: bool = False
    timeseries: bool = False
    watchlist: bool = False
    movers: bool = False
    dataadmin: bool = False
    virtual: bool = False
    support: bool = False
    scenario: bool = False
    reports: bool = False


@dataclass
class Config:
    # basic app environment
    app_env: Optional[str] = None

    # messaging / alerts
    sns_topic_arn: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # paths / app settings
    portfolio_xml_path: Optional[str] = None
    transactions_output_root: Optional[str] = None
    uvicorn_port: Optional[int] = None
    reload: Optional[bool] = None
    log_config: Optional[str] = None
    skip_snapshot_warm: Optional[bool] = None
    snapshot_warm_days: Optional[int] = None

    # scraping / automation
    ft_url_template: Optional[str] = None
    selenium_user_agent: Optional[str] = None
    selenium_headless: Optional[bool] = None

    # misc complex config
    error_summary: Optional[dict] = None
    offline_mode: Optional[bool] = None
    relative_view_enabled: Optional[bool] = None
    theme: Optional[str] = None
    timeseries_cache_base: Optional[str] = None
    fx_proxy_url: Optional[str] = None
    alpha_vantage_key: Optional[str] = None
    fundamentals_cache_ttl_seconds: Optional[int] = None

    # new vars
    max_trades_per_month: Optional[int] = None
    hold_days_min: Optional[int] = None
    repo_root: Optional[Path] = None
    accounts_root: Optional[Path] = None
    prices_json: Optional[Path] = None
    risk_free_rate: Optional[float] = None

    approval_valid_days: Optional[int] = None
    approval_exempt_types: Optional[List[str]] = None
    approval_exempt_tickers: Optional[List[str]] = None
    tabs: TabsConfig = field(default_factory=TabsConfig)
    cors_origins: Optional[List[str]] = None


def _project_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> Config:
    """Load configuration from config.yaml with environment overrides."""
    path = _project_config_path()
    data: Dict[str, Any] = {}

    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                file_data = yaml.safe_load(f) or {}
                if isinstance(file_data, dict):
                    data.update(file_data)
        except Exception:
            pass

    base_dir = path.parent

    repo_root_raw = data.get("repo_root")
    repo_root = (base_dir / repo_root_raw).resolve() if repo_root_raw else base_dir

    accounts_root_raw = data.get("accounts_root")
    accounts_root = (repo_root / accounts_root_raw).resolve() if accounts_root_raw else None

    prices_json_raw = data.get("prices_json")
    prices_json = (repo_root / prices_json_raw).resolve() if prices_json_raw else None

    tabs_raw = data.get("tabs")
    tabs_data = asdict(TabsConfig())
    if isinstance(tabs_raw, dict):
        tabs_data.update(tabs_raw)
    tabs = TabsConfig(**tabs_data)

    cors_raw = data.get("cors")
    cors_origins = None
    if isinstance(cors_raw, dict):
        env = data.get("app_env")
        if env:
            cors_origins = cors_raw.get(env) or cors_raw.get("default")
        else:
            cors_origins = cors_raw.get("default")

    alpha_vantage_key = os.getenv("ALPHA_VANTAGE_KEY") or data.get("alpha_vantage_key")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or data.get("telegram_bot_token")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID") or data.get("telegram_chat_id")
    sns_topic_arn = os.getenv("SNS_TOPIC_ARN") or data.get("sns_topic_arn")

    return Config(
        app_env=data.get("app_env"),
        sns_topic_arn=sns_topic_arn,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        portfolio_xml_path=data.get("portfolio_xml_path"),
        transactions_output_root=data.get("transactions_output_root"),
        uvicorn_port=data.get("uvicorn_port"),
        reload=data.get("reload"),
        log_config=data.get("log_config"),
        skip_snapshot_warm=data.get("skip_snapshot_warm"),
        snapshot_warm_days=data.get("snapshot_warm_days"),
        ft_url_template=data.get("ft_url_template"),
        selenium_user_agent=data.get("selenium_user_agent"),
        selenium_headless=data.get("selenium_headless"),
        error_summary=data.get("error_summary"),
        offline_mode=data.get("offline_mode"),
        relative_view_enabled=data.get("relative_view_enabled"),
        theme=data.get("theme"),
        timeseries_cache_base=data.get("timeseries_cache_base"),
        fx_proxy_url=data.get("fx_proxy_url"),
        alpha_vantage_key=alpha_vantage_key,
        fundamentals_cache_ttl_seconds=data.get("fundamentals_cache_ttl_seconds"),
        max_trades_per_month=data.get("max_trades_per_month"),
        hold_days_min=data.get("hold_days_min"),
        repo_root=repo_root,
        accounts_root=accounts_root,
        prices_json=prices_json,
        risk_free_rate=data.get("risk_free_rate"),
        approval_valid_days=data.get("approval_valid_days"),
        approval_exempt_types=data.get("approval_exempt_types"),
        approval_exempt_tickers=data.get("approval_exempt_tickers"),
        tabs=tabs,
        cors_origins=cors_origins,
    )


# New-style usage
config = load_config()
settings = config


# ---- Back-compat helpers ----
def get_config_dict() -> Dict[str, Any]:
    """Return the config as a plain dict."""
    return asdict(load_config())


@overload
def get_config() -> Dict[str, Any]: ...
@overload
def get_config(key: str, default: Any = None) -> Any: ...


def get_config(key: Optional[str] = None, default: Any = None):
    """
    Backward-compatible accessor.
      get_config() -> dict
      get_config("key") -> value or default
    """
    d = get_config_dict()
    if key is None:
        return d
    return d.get(key, default)
