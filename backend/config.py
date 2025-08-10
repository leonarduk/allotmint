from __future__ import annotations

from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, overload
import yaml


@dataclass(frozen=True)
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

    # scraping / automation
    ft_url_template: Optional[str] = None
    selenium_user_agent: Optional[str] = None
    selenium_headless: Optional[bool] = None

    # misc complex config
    error_summary: Optional[dict] = None
    offline_mode: Optional[bool] = None
    timeseries_cache_base: Optional[str] = None
    alpha_vantage_key: Optional[str] = None
    alpha_vantage_fundamentals_cache_ttl_seconds: Optional[int] = None

    # new vars
    max_trades_per_month: Optional[int] = None
    hold_days_min: Optional[int] = None
    repo_root: Optional[Path] = None
    accounts_root: Optional[Path] = None
    prices_json: Optional[Path] = None


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
        ft_url_template=data.get("ft_url_template"),
        selenium_user_agent=data.get("selenium_user_agent"),
        selenium_headless=data.get("selenium_headless"),
        error_summary=data.get("error_summary"),
        offline_mode=data.get("offline_mode"),
        timeseries_cache_base=data.get("timeseries_cache_base"),
        alpha_vantage_key=data.get("alpha_vantage_key"),
        alpha_vantage_fundamentals_cache_ttl_seconds=data.get(
            "alpha_vantage_fundamentals_cache_ttl_seconds"
        ),
        max_trades_per_month=data.get("max_trades_per_month"),
        hold_days_min=data.get("hold_days_min"),
        repo_root=Path(data["repo_root"]) if data.get("repo_root") else None,
        accounts_root=Path(data["accounts_root"]) if data.get("accounts_root") else None,
        prices_json=Path(data["prices_json"]) if data.get("prices_json") else None,
    )


# New-style usage
config = load_config()


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
