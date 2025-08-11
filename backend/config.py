from __future__ import annotations

from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, overload, List
import yaml


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
    timeseries_cache_base: Optional[str] = None
    alpha_vantage_key: Optional[str] = None
    fundamentals_cache_ttl_seconds: Optional[int] = None

    # new vars
    max_trades_per_month: Optional[int] = None
    hold_days_min: Optional[int] = None
    repo_root: Optional[Path] = None
    accounts_root: Optional[Path] = None
    prices_json: Optional[Path] = None

    approval_valid_days: Optional[int] = None
    approval_exempt_types: Optional[List[str]] = None
    approval_exempt_tickers: Optional[List[str]] = None


def _project_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> Config:
    """Load configuration from config.yaml only (no env overrides)."""
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
    accounts_root = (
        (repo_root / accounts_root_raw).resolve() if accounts_root_raw else None
    )

    prices_json_raw = data.get("prices_json")
        prices_json = (
            (repo_root / prices_json_raw).resolve() if prices_json_raw else None
        )

    return Config(
        app_env=data.get("app_env"),
        sns_topic_arn=data.get("sns_topic_arn"),
        telegram_bot_token=data.get("telegram_bot_token"),
        telegram_chat_id=data.get("telegram_chat_id"),
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
        timeseries_cache_base=data.get("timeseries_cache_base"),
        alpha_vantage_key=data.get("alpha_vantage_key"),
        fundamentals_cache_ttl_seconds=data.get(
            "fundamentals_cache_ttl_seconds"
        ),
        max_trades_per_month=data.get("max_trades_per_month"),
        hold_days_min=data.get("hold_days_min"),
        repo_root=repo_root,
        accounts_root=accounts_root,
        prices_json=prices_json,
        approval_valid_days=data.get("approval_valid_days"),
        approval_exempt_types=data.get("approval_exempt_types"),
        approval_exempt_tickers=data.get("approval_exempt_tickers"),
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
