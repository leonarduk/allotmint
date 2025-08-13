from __future__ import annotations

"""Data loading helpers for AllotMint."""

from pathlib import Path
import json
from typing import Any, Dict, List

from backend.config import config

from backend.common.virtual_portfolio import VirtualPortfolio

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
REPO_ROOT = Path(config.repo_root)
DATA_ROOT = Path(config.accounts_root)
_VIRTUAL_PF_ROOT = REPO_ROOT / "data" / "virtual_portfolios"

# For future AWS use
DATA_BUCKET_ENV = "DATA_BUCKET"
PLOTS_PREFIX = "accounts/"


# ------------------------------------------------------------------
# Local discovery
# ------------------------------------------------------------------
_METADATA_STEMS = {"person", "config", "notes"}  # ignore these as accounts


def _list_local_plots() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not DATA_ROOT.exists():
        return results

    for owner_dir in sorted(DATA_ROOT.iterdir()):
        if not owner_dir.is_dir():
            continue

        acct_names: List[str] = []
        for f in sorted(owner_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() != ".json":
                continue

            stem = f.stem
            if stem.lower() in _METADATA_STEMS:
                continue

            acct_names.append(stem)

        # Dedupe case-insensitive, preserve first occurrence order
        seen: set[str] = set()
        dedup: List[str] = []
        for a in acct_names:
            al = a.lower()
            if al in seen:
                continue
            seen.add(al)
            dedup.append(a)

        results.append({
            "owner": owner_dir.name,
            "accounts": dedup,
        })

    return results


# ------------------------------------------------------------------
# AWS discovery (stub)
# ------------------------------------------------------------------
def _list_aws_plots() -> List[Dict[str, Any]]:
    # TODO: implement S3 listing
    return []


# ------------------------------------------------------------------
# Public discovery API
# ------------------------------------------------------------------
def list_plots() -> List[Dict[str, Any]]:
    if config.app_env == "aws":
        return _list_aws_plots()
    return _list_local_plots()


# ------------------------------------------------------------------
# Load JSON w/ safe parser (strip BOM, allow empty)
# ------------------------------------------------------------------
def _safe_json_load(path: Path) -> Dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(str(path))
    with open(path, "r", encoding="utf-8-sig") as f:  # utf-8-sig strips BOM
        txt = f.read().strip()
    if not txt:
        raise ValueError(f"Empty JSON file: {path}")
    return json.loads(txt)


# ------------------------------------------------------------------
# Account loaders
# ------------------------------------------------------------------
def load_account(owner: str, account: str) -> Dict[str, Any]:
    if config.app_env == "aws":
        # TODO: S3
        raise FileNotFoundError(
            f"AWS account loading not implemented: {owner}/{account}"
        )

    path = DATA_ROOT / owner / f"{account}.json"
    return _safe_json_load(path)


def load_person_meta(owner: str) -> Dict[str, Any]:
    """Load per-owner metadata (dob, etc.). Returns {} if not found."""
    if config.app_env == "aws":
        # TODO: S3
        return {}
    path = DATA_ROOT / owner / "person.json"
    if not path.exists():
        return {}
    try:
        return _safe_json_load(path)
    except Exception:
        return {}


# ------------------------------------------------------------------
# Virtual portfolio helpers
# ------------------------------------------------------------------


def _virtual_portfolio_path(name: str) -> Path:
    return _VIRTUAL_PF_ROOT / f"{name}.json"


def list_virtual_portfolios() -> list[str]:
    if not _VIRTUAL_PF_ROOT.exists():
        return []
    return sorted(p.stem for p in _VIRTUAL_PF_ROOT.glob("*.json"))


def load_virtual_portfolio(name: str) -> VirtualPortfolio:
    path = _virtual_portfolio_path(name)
    data = _safe_json_load(path)
    return VirtualPortfolio.model_validate(data)


def save_virtual_portfolio(pf: VirtualPortfolio) -> None:
    _VIRTUAL_PF_ROOT.mkdir(parents=True, exist_ok=True)
    path = _virtual_portfolio_path(pf.name)
    path.write_text(pf.model_dump_json(indent=2))
