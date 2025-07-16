"""
Shared data-loading functions for AllotMint.

Reads JSON account files from:
- local filesystem (dev mode)
- S3 bucket (aws mode)

ENV VARS:
  ALLOTMINT_ENV = 'local' | 'aws'  (default: local)
  DATA_BUCKET   = S3 bucket name (aws mode only)
"""

import json
import os
import pathlib
from typing import Any, Dict, List, TypedDict

try:
    import boto3  # available in aws mode
except ImportError:
    boto3 = None  # local mode may not have it yet


class PlotInfo(TypedDict, total=False):
    owner: str
    accounts: List[str]


# Resolve repo root -> data-sample path
# backend/common/data_loader.py is 2 levels down from repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_LOCAL_PLOTS_ROOT = _REPO_ROOT / "data-sample" / "plots"


# -----------------------
# Internal helpers
# -----------------------
def _load_local_json(owner: str, account_filename: str) -> Dict[str, Any]:
    path = _LOCAL_PLOTS_ROOT / owner / account_filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_s3_json(owner: str, account_filename: str) -> Dict[str, Any]:
    if boto3 is None:
        raise RuntimeError("boto3 not installed; cannot load from S3 in this environment.")
    bucket = os.environ["DATA_BUCKET"]
    key = f"plots/{owner}/{account_filename}"
    s3 = boto3.client("s3")
    resp = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(resp["Body"].read())


def _list_local_plots() -> List[PlotInfo]:
    plots: List[PlotInfo] = []
    if not _LOCAL_PLOTS_ROOT.exists():
        return plots
    for owner_dir in _LOCAL_PLOTS_ROOT.iterdir():
        if not owner_dir.is_dir():
            continue
        owner = owner_dir.name
        accounts = []
        for f in owner_dir.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() != ".json":
                continue  # skip csv etc
            accounts.append(f.stem)  # filename without .json
        plots.append({"owner": owner, "accounts": sorted(accounts)})
    return sorted(plots, key=lambda p: p["owner"])


def _list_s3_plots() -> List[PlotInfo]:
    if boto3 is None:
        raise RuntimeError("boto3 not installed; cannot list from S3 in this environment.")
    bucket = os.environ["DATA_BUCKET"]
    prefix = "plots/"
    s3 = boto3.client("s3")

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    # Accumulate {owner: set(accounts)}
    owners: Dict[str, set[str]] = {}
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]  # e.g. plots/stephen/isa.json
            parts = key.split("/")
            if len(parts) != 3:
                continue
            _, owner, filename = parts
            if not filename.endswith(".json"):
                continue
            acct = filename[:-5]  # strip .json
            owners.setdefault(owner, set()).add(acct)

    plots: List[PlotInfo] = []
    for owner, acct_set in owners.items():
        plots.append({"owner": owner, "accounts": sorted(acct_set)})
    return sorted(plots, key=lambda p: p["owner"])


# -----------------------
# Public API
# -----------------------
def load_account(owner: str, account: str, env: str | None = None) -> Dict[str, Any]:
    """
    Load one account JSON (e.g., isa.json, sipp.json) for an owner.

    account: 'isa' | 'sipp' | 'pension-forecast' (filename minus .json)
    """
    env = env or os.getenv("ALLOTMINT_ENV", "local").lower()
    filename = f"{account}.json"
    if env == "aws":
        return _load_s3_json(owner, filename)
    return _load_local_json(owner, filename)


def list_plots(env: str | None = None) -> List[PlotInfo]:
    """
    Return a list of owners and their available account files.
    """
    env = env or os.getenv("ALLOTMINT_ENV", "local").lower()
    if env == "aws":
        return _list_s3_plots()
    return _list_local_plots()
