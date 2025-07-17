from __future__ import annotations

"""
Data loading helpers for AllotMint.

Supports two environments:
- local: read from data-sample/plots/<owner>/
- aws:   (future) read from S3

Functions exported:
- list_plots(env=None) -> [{owner, accounts:[...]}, ...]
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
_LOCAL_PLOTS_ROOT = _REPO_ROOT / "data-sample" / "plots"

# For future AWS use
DATA_BUCKET_ENV = "DATA_BUCKET"
PLOTS_PREFIX = "plots/"


# ------------------------------------------------------------------
# Local discovery
# ------------------------------------------------------------------
_METADATA_STEMS = {"person", "config", "notes"}  # ignore these as accounts


def _list_local_plots() -> List[Dict[str, Any]]:
    plots: List[Dict[str, Any]] = []
    if not _LOCAL_PLOTS_ROOT.exists():
        return plots

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

        plots.append({
            "owner": owner_dir.name,
            "accounts": dedup,
        })

    return plots


# ------------------------------------------------------------------
# AWS discovery (stub)
# ------------------------------------------------------------------
def _list_aws_plots() -> List[Dict[str, Any]]:
    # TODO: implement S3 listing
    return []


# ------------------------------------------------------------------
# Public discovery API
# ------------------------------------------------------------------
def list_plots(env: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Return list of owners + account names.
    """
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    if env == "aws":
        return _list_aws_plots()
    return _list_local_plots()


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
