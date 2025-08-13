from __future__ import annotations

"""Data loading helpers for AllotMint."""

from pathlib import Path
import json
import os
from typing import Any, Dict, List

from backend.config import config

from backend.common.virtual_portfolio import VirtualPortfolio

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
if config.repo_root and ":" not in str(config.repo_root) and Path(config.repo_root).exists():
    REPO_ROOT = Path(config.repo_root)
else:
    REPO_ROOT = Path(__file__).resolve().parents[2]

# Ensure other modules see the resolved repo root
try:
    config.repo_root = REPO_ROOT
except Exception:
    pass

if config.accounts_root and ":" not in str(config.accounts_root) and Path(config.accounts_root).exists():
    DATA_ROOT = Path(config.accounts_root)
else:
    DATA_ROOT = REPO_ROOT / "data" / "accounts"

# Ensure other modules see the resolved accounts root
try:
    config.accounts_root = DATA_ROOT
except Exception:
    pass
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
# AWS discovery
# ------------------------------------------------------------------
def _list_aws_plots() -> List[Dict[str, Any]]:
    """List available plots from an S3 bucket.

    The bucket name is read from the ``DATA_BUCKET`` environment variable and
    objects are expected under ``accounts/<owner>/<account>.json``. Metadata
    files like ``person.json`` are ignored and account names are de-duplicated
    case-insensitively.
    """

    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        return []
    try:
        import boto3  # type: ignore
    except Exception:
        return []

    s3 = boto3.client("s3")
    owners: Dict[str, List[str]] = {}
    token: str | None = None

    while True:
        params = {"Bucket": bucket, "Prefix": PLOTS_PREFIX}
        if token:
            params["ContinuationToken"] = token
        resp = s3.list_objects_v2(**params)
        for item in resp.get("Contents", []):
            key = item.get("Key", "")
            if not key.lower().endswith(".json"):
                continue
            if not key.startswith(PLOTS_PREFIX):
                continue
            rel = key[len(PLOTS_PREFIX) :]
            parts = rel.split("/")
            if len(parts) != 2:
                continue
            owner, filename = parts
            stem = Path(filename).stem
            if stem.lower() in _METADATA_STEMS:
                continue
            accounts = owners.setdefault(owner, [])
            lower = stem.lower()
            if all(existing.lower() != lower for existing in accounts):
                accounts.append(stem)
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break

    return [
        {"owner": owner, "accounts": accounts}
        for owner, accounts in sorted(owners.items())
    ]


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
        bucket = os.getenv(DATA_BUCKET_ENV)
        if not bucket:
            raise FileNotFoundError(
                f"Missing {DATA_BUCKET_ENV} env var for AWS account loading"
            )
        key = f"{PLOTS_PREFIX}{owner}/{account}.json"
        try:
            import boto3  # type: ignore
            obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        except Exception as exc:  # pragma: no cover - exercised via tests
            raise FileNotFoundError(f"s3://{bucket}/{key}") from exc
        body = obj.get("Body")
        txt = body.read().decode("utf-8-sig").strip() if body else ""
        if not txt:
            raise ValueError(f"Empty JSON file: s3://{bucket}/{key}")
        return json.loads(txt)

    path = DATA_ROOT / owner / f"{account}.json"
    return _safe_json_load(path)


def load_person_meta(owner: str) -> Dict[str, Any]:
    """Load per-owner metadata (dob, etc.). Returns {} if not found."""
    if config.app_env == "aws":
        bucket = os.getenv(DATA_BUCKET_ENV)
        if not bucket:
            return {}
        key = f"{PLOTS_PREFIX}{owner}/person.json"
        try:
            import boto3  # type: ignore
            obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
            body = obj.get("Body")
            txt = body.read().decode("utf-8-sig").strip() if body else ""
            if not txt:
                return {}
            return json.loads(txt)
        except Exception:
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
