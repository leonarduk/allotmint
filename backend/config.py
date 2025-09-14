from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigValidationError(ValueError):
    """Raised when configuration values are invalid."""


def validate_google_auth(enabled: Optional[bool], client_id: Optional[str]) -> None:
    """Ensure Google auth is configured correctly."""
    if enabled:
        if not client_id or not client_id.strip():
            raise ConfigValidationError("google_auth_enabled is true but google_client_id is missing")


def validate_tabs(tabs_raw: Any) -> TabsConfig:
    """Validate tab configuration ensuring all keys are known booleans."""
    tabs_data = asdict(TabsConfig())
    if isinstance(tabs_raw, dict):
        for key, val in tabs_raw.items():
            if key not in tabs_data:
                raise ConfigValidationError(f"Unknown tab '{key}'")
            if not isinstance(val, bool):
                raise ConfigValidationError(f"Tab '{key}' must be a boolean")
            tabs_data[key] = val
    return TabsConfig(**tabs_data)


@dataclass
class TabsConfig:
    instrument: bool = True
    performance: bool = True
    transactions: bool = True
    screener: bool = True
    query: bool = True
    trading: bool = True
    timeseries: bool = True
    watchlist: bool = True
    movers: bool = True
    market: bool = True
    allocation: bool = True
    rebalance: bool = True
    instrumentadmin: bool = True
    group: bool = True
    owner: bool = True
    dataadmin: bool = True
    virtual: bool = True
    support: bool = True
    settings: bool = True
    profile: bool = False
    pension: bool = True
    reports: bool = True
    scenario: bool = True
    logs: bool = True


@dataclass
class TradingAgentConfig:
    rsi_buy: float = 30.0
    rsi_sell: float = 70.0
    rsi_window: int = 14
    ma_short_window: int = 20
    ma_long_window: int = 50
    pe_max: Optional[float] = None
    de_max: Optional[float] = None
    min_sharpe: Optional[float] = None
    max_volatility: Optional[float] = None


@dataclass
class Config:
    # basic app environment
    app_env: Optional[str] = None

    # messaging / alerts
    sns_topic_arn: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # paths / app settings
    portfolio_xml_path: Optional[Path] = None
    transactions_output_root: Optional[Path] = None
    uvicorn_port: Optional[int] = None
    reload: Optional[bool] = None
    rate_limit_per_minute: int = 6000
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
    google_auth_enabled: Optional[bool] = None
    disable_auth: Optional[bool] = None
    google_client_id: Optional[str] = None
    relative_view_enabled: Optional[bool] = None
    theme: Optional[str] = None
    timeseries_cache_base: Optional[str] = None
    fx_proxy_url: Optional[str] = None

    alpha_vantage_enabled: Optional[bool] = None
    alpha_vantage_key: Optional[str] = None
    fundamentals_cache_ttl_seconds: Optional[int] = None
    stooq_timeout: Optional[int] = None
    news_requests_per_day: int = 25

    # new vars
    max_trades_per_month: Optional[int] = None
    hold_days_min: Optional[int] = None
    repo_root: Optional[Path] = None
    data_root: Optional[Path] = None
    accounts_root: Optional[Path] = None
    prices_json: Optional[Path] = None
    risk_free_rate: Optional[float] = None
    base_currency: Optional[str] = "GBP"

    approval_valid_days: Optional[int] = None
    approval_exempt_types: Optional[List[str]] = None
    approval_exempt_tickers: Optional[List[str]] = None
    tabs: TabsConfig = field(default_factory=TabsConfig)
    trading_agent: TradingAgentConfig = field(default_factory=TradingAgentConfig)
    cors_origins: Optional[List[str]] = None


def _project_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config.yaml"


def _env_flag(name: str) -> Optional[bool]:
    val = os.getenv(name)
    if val is None:
        return None
    return val.lower() in {"1", "true", "yes"}


def _flatten_dict(src: Dict[str, Any], dst: Dict[str, Any]) -> None:
    """Flatten one level of ``src`` into ``dst`` while preserving nested maps."""
    for key, value in src.items():
        if isinstance(value, dict):
            for sub_key, sub_val in value.items():
                dst[sub_key] = sub_val
        else:
            dst[key] = value


def _parse_str_list(val: Any) -> Optional[List[str]]:
    """Convert comma-separated strings or lists into list of strings."""
    if isinstance(val, list):
        items = [str(v).strip() for v in val if str(v).strip()]
        return items or []
    if isinstance(val, str):
        items = [s.strip() for s in val.split(",") if s.strip()]
        return items or []
    return None


def _load_config() -> Config:
    """Load configuration from config.yaml with optional env overrides."""
    path = _project_config_path()
    data: Dict[str, Any] = {}

    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                file_data = yaml.safe_load(f) or {}
                if isinstance(file_data, dict):
                    _flatten_dict(file_data, data)
        except yaml.YAMLError as exc:
            logger.exception("Failed to parse config file %s", path)
            raise ConfigValidationError(f"Error parsing config file '{path}': {exc}") from exc
        except OSError as exc:
            logger.exception("Failed to read config file %s", path)
            raise ConfigValidationError(f"Error reading config file '{path}': {exc}") from exc

    base_dir = path.parent

    app_env_env = os.getenv("APP_ENV")
    if app_env_env:
        allowed_envs = {"local", "production", "aws"}
        if app_env_env not in allowed_envs:
            raise ValueError(f"Unexpected APP_ENV '{app_env_env}'")
        data["app_env"] = app_env_env

    disable_auth_env = _env_flag("DISABLE_AUTH")
    if disable_auth_env is not None:
        data["disable_auth"] = disable_auth_env

    telegram_token_env = os.getenv("TELEGRAM_BOT_TOKEN")
    if telegram_token_env is not None:
        data["telegram_bot_token"] = telegram_token_env

    telegram_chat_id_env = os.getenv("TELEGRAM_CHAT_ID")
    if telegram_chat_id_env is not None:
        data["telegram_chat_id"] = telegram_chat_id_env

    repo_root_raw = data.get("repo_root")
    repo_root = (base_dir / repo_root_raw).resolve() if repo_root_raw else base_dir

    data_root_raw = data.get("data_root") or "data"
    env_data_root = os.getenv("DATA_ROOT")
    if env_data_root:
        data_root_raw = env_data_root
    data_root_path = Path(data_root_raw)
    data_root = (data_root_path if data_root_path.is_absolute() else (repo_root / data_root_path)).resolve()

    accounts_root_raw = data.get("accounts_root")
    accounts_root = (data_root / accounts_root_raw).resolve() if accounts_root_raw else None

    prices_json_raw = data.get("prices_json")
    prices_json = (data_root / prices_json_raw).resolve() if prices_json_raw else None

    ts_cache_raw = data.get("timeseries_cache_base")
    env_ts_cache = os.getenv("TIMESERIES_CACHE_BASE")
    if env_ts_cache:
        timeseries_cache_base = env_ts_cache
    else:
        timeseries_cache_base = (
            str((data_root / ts_cache_raw).resolve()) if ts_cache_raw else None
        )

    portfolio_xml_raw = data.get("portfolio_xml_path")
    portfolio_xml_path = (data_root / portfolio_xml_raw).resolve() if portfolio_xml_raw else None

    tx_output_raw = data.get("transactions_output_root")
    transactions_output_root = (data_root / tx_output_raw).resolve() if tx_output_raw else None

    tabs_raw = data.get("tabs")
    tabs = validate_tabs(tabs_raw)

    ta_raw = data.get("trading_agent")
    ta_data = asdict(TradingAgentConfig())
    if isinstance(ta_raw, dict):
        ta_data.update(ta_raw)
    trading_agent = TradingAgentConfig(**ta_data)

    cors_raw = data.get("cors")
    cors_origins = None
    if isinstance(cors_raw, dict):
        env = data.get("app_env")
        if env:
            cors_origins = cors_raw.get(env) or cors_raw.get("default")
        else:
            cors_origins = cors_raw.get("default")

    approval_exempt_types = _parse_str_list(data.get("approval_exempt_types"))
    approval_exempt_tickers = _parse_str_list(data.get("approval_exempt_tickers"))

    google_auth_enabled = data.get("google_auth_enabled")
    env_google_auth = os.getenv("GOOGLE_AUTH_ENABLED")
    if env_google_auth is not None:
        env_val = env_google_auth.strip().lower()
        if env_val in {"1", "true", "yes"}:
            google_auth_enabled = True
        elif env_val in {"0", "false", "no"}:
            google_auth_enabled = False
        else:
            raise ConfigValidationError(
                f"GOOGLE_AUTH_ENABLED must be one of: '1', 'true', 'yes', '0', 'false', 'no' (case-insensitive); got '{env_google_auth}'",
            )

    google_client_id = data.get("google_client_id")
    env_client_id = os.getenv("GOOGLE_CLIENT_ID")
    if env_client_id is not None:
        google_client_id = env_client_id

    if isinstance(google_client_id, str):
        google_client_id = google_client_id.strip() or None

    validate_google_auth(google_auth_enabled, google_client_id)

    # Optional env override for Alpha Vantage API key to avoid committing secrets
    alpha_key_env = os.getenv("ALPHA_VANTAGE_KEY")
    if alpha_key_env:
        data["alpha_vantage_key"] = alpha_key_env

    cfg = Config(
        app_env=data.get("app_env"),
        sns_topic_arn=data.get("sns_topic_arn"),
        telegram_bot_token=data.get("telegram_bot_token"),
        telegram_chat_id=data.get("telegram_chat_id"),
        portfolio_xml_path=portfolio_xml_path,
        transactions_output_root=transactions_output_root,
        uvicorn_port=data.get("uvicorn_port"),
        reload=data.get("reload"),
        rate_limit_per_minute=data.get("rate_limit_per_minute", 60),
        log_config=data.get("log_config"),
        skip_snapshot_warm=data.get("skip_snapshot_warm"),
        snapshot_warm_days=data.get("snapshot_warm_days"),
        ft_url_template=data.get("ft_url_template"),
        selenium_user_agent=data.get("selenium_user_agent"),
        selenium_headless=data.get("selenium_headless"),
        error_summary=data.get("error_summary"),
        offline_mode=data.get("offline_mode"),
        disable_auth=data.get("disable_auth"),
        google_auth_enabled=google_auth_enabled,
        google_client_id=google_client_id,
        relative_view_enabled=data.get("relative_view_enabled"),
        theme=data.get("theme"),
        timeseries_cache_base=timeseries_cache_base,
        fx_proxy_url=data.get("fx_proxy_url"),
        alpha_vantage_key=data.get("alpha_vantage_key"),
        fundamentals_cache_ttl_seconds=data.get("fundamentals_cache_ttl_seconds"),
        stooq_timeout=data.get("stooq_timeout"),
        news_requests_per_day=data.get("news_requests_per_day", 25),
        max_trades_per_month=data.get("max_trades_per_month"),
        hold_days_min=data.get("hold_days_min"),
        repo_root=repo_root,
        data_root=data_root,
        accounts_root=accounts_root,
        prices_json=prices_json,
        risk_free_rate=data.get("risk_free_rate"),
        approval_valid_days=data.get("approval_valid_days"),
        approval_exempt_types=approval_exempt_types,
        approval_exempt_tickers=approval_exempt_tickers,
        tabs=tabs,
        trading_agent=trading_agent,
        cors_origins=cors_origins,
    )


    return cfg


@lru_cache()
def load_config() -> Config:
    """Load configuration and cache the result."""
    return _load_config()

settings = load_config()
config = settings


def reload_config() -> Config:
    """Reload configuration and update module-level ``config``."""
    global config, settings
    load_config.cache_clear()
    new_config = load_config()
    config = settings = new_config
    return new_config


def __getattr__(name: str) -> Any:
    try:
        return getattr(load_config(), name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

