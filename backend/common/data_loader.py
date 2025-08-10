from __future__ import annotations

"""
Data loading helpers for AllotMint.

Supports two environments:
- local: read from data/accounts/<owner>/
- aws:   (future) read from S3

Functions exported:
- list_accounts(env=None) -> [{owner, accounts:[...]}, ...]
- load_account(owner, account, env=None) -> dict (parsed JSON)
- load_person_meta(owner, env=None) -> dict (parsed JSON or {})

The "account name" is derived from the filename stem (isa.json -> "isa").
Metadata files (person.json, config.json, notes.json) are ignored.
Duplicate names (case-insensitive) are deduped in discovery.
"""

import os
import pathlib
from typing import Any, Dict, List, Optional

from backend.common.virtual_portfolio import VirtualPortfolio

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_LOCAL_PLOTS_ROOT = _REPO_ROOT / "data" / "accounts"
_VIRTUAL_PF_ROOT = _REPO_ROOT / "data" / "virtual_portfolios"

# For future AWS use
DATA_BUCKET_ENV = "DATA_BUCKET"
PLOTS_PREFIX = "accounts/"


# ------------------------------------------------------------------
# Local discovery
# ------------------------------------------------------------------
_METADATA_STEMS = {"person", "config", "notes"}  # ignore these as accounts


def _list_local_plots() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not _LOCAL_PLOTS_ROOT.exists():
        return results

    for owner_dir in sorted(_LOCAL_PLOTS_ROOT.iterdir()):
        if not owner_dir.is_dir():
            continue

        acct_names: List[str] = []
        for f in sorted(owner_dir.iterdir()):
            if not f.is_file():
                continue
            # CSV ignored for account discovery (trades)
            if f.suffix.lower() != ".json":
                continue

            stem = f.stem  # original (preserve case for display)
            stem_l = stem.lower()
            if stem_l in _METADATA_STEMS:
                continue

            acct_names.append(stem)

        # Dedupe case-insensitive, preserve first occurrence order
        seen = set()
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
from pathlib import Path
import json

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "accounts"

# backend/common/data_loader.py  (or wherever list_plots lives)

from pathlib import Path
import json

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "accounts"

# backend/common/data_loader.py
def list_plots(env: str | None = None) -> list[dict]:   # 👈 keep callers happy
    owners: list[dict] = []
    for owner_dir in DATA_ROOT.iterdir():
        if not (owner_dir / "person.json").exists():
            continue          # skip stray folders
        # ── person metadata ──────────────────────────────
        person = json.loads((owner_dir / "person.json").read_text())
        # ── account files  (anything *.json except person.json) ──
        accounts = [
            f.stem             # "isa", "sipp", ...
            for f in owner_dir.glob("*.json")
            if f.name != "person.json"
        ]
        owners.append({**person, "accounts": accounts})
    return owners


# ------------------------------------------------------------------
# Load JSON w/ safe parser (strip BOM, allow empty)
# ------------------------------------------------------------------
def _safe_json_load(path: pathlib.Path) -> Dict[str, Any]:
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
def load_account(owner: str, account: str, env: Optional[str] = None) -> Dict[str, Any]:
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    if env == "aws":
        # TODO: S3
        raise FileNotFoundError(f"AWS account loading not implemented: {owner}/{account}")

    path = _LOCAL_PLOTS_ROOT / owner / f"{account}.json"
    return _safe_json_load(path)


def load_person_meta(owner: str, env: Optional[str] = None) -> Dict[str, Any]:
    """
    Load per-owner metadata (dob, etc.). Returns {} if not found.
    """
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    if env == "aws":
        # TODO: S3
        return {}
    path = _LOCAL_PLOTS_ROOT / owner / "person.json"
    if not path.exists():
        return {}
    try:
        return _safe_json_load(path)
    except Exception:
        return {}


# ------------------------------------------------------------------
# Virtual portfolio helpers
# ------------------------------------------------------------------


def _virtual_portfolio_path(name: str) -> pathlib.Path:
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
