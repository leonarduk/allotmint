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

import json
import os
import pathlib
from typing import Any, Dict, List, Optional

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_LOCAL_PLOTS_ROOT = _REPO_ROOT / "data" / "accounts"

# For future AWS use
DATA_BUCKET_ENV = "DATA_BUCKET"
PLOTS_PREFIX = "accounts/"


# ------------------------------------------------------------------
# Local discovery
# ------------------------------------------------------------------
_METADATA_STEMS = {"person", "config", "notes"}  # ignore these as accounts


def _list_local_plots() -> List[Dict[str, Any]]:
    accounts: List[Dict[str, Any]] = []
    if not _LOCAL_PLOTS_ROOT.exists():
        return accounts

    for owner_dir in sorted(_LOCAL_PLOTS_ROOT.iterdir()):
        if not owner_dir.is_dir():
            continue

        accounts: List[str] = []
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

            accounts.append(stem)

        # Dedupe case-insensitive, preserve first occurrence order
        seen = set()
        dedup: List[str] = []
        for a in accounts:
            al = a.lower()
            if al in seen:
                continue
            seen.add(al)
            dedup.append(a)

        accounts.append({
            "owner": owner_dir.name,
            "accounts": dedup,
        })

    return accounts


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

def list_plots(env: str = "local") -> list[dict]:
    plots = []
    for owner_dir in DATA_ROOT.iterdir():
        if not owner_dir.is_dir():
            continue

        person_file = owner_dir / "person.json"
        if not person_file.exists():
            continue

        try:
            with open(person_file) as f:
                info = json.load(f)
        except Exception:
            continue

        # infer accounts by listing all *.json files EXCEPT 'person.json'
        account_files = [
            f.stem.lower()
            for f in owner_dir.glob("*.json")
            if f.name != "person.json"
        ]

        plots.append({
            "owner": info.get("owner") or owner_dir.name,
            "accounts": sorted(account_files),
        })

    return plots


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
