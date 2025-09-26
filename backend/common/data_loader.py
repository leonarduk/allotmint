from __future__ import annotations

"""Data loading helpers for AllotMint."""

import json
import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List, Optional

from backend.common.virtual_portfolio import VirtualPortfolio
from backend.config import config


# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedPaths:
    repo_root: Path
    accounts_root: Path
    virtual_pf_root: Path


def resolve_paths(
    repo_root: Optional[Path | str] = None,
    accounts_root: Optional[Path | str] = None,
) -> ResolvedPaths:
    """Return fully resolved repository and accounts paths.

    ``repo_root`` is treated as the base of the repository. If ``None`` or the
    supplied path does not exist the function falls back to the actual
    repository root relative to this file. ``accounts_root`` may be an absolute
    path or a path relative to ``repo_root``. Windows-style absolute paths are
    handled even when running on a POSIX platform.
    """

    if repo_root and Path(repo_root).exists():
        repo_path = Path(repo_root).expanduser()
    else:
        repo_path = Path(__file__).resolve().parents[2]

    data_root = repo_path / "data"

    if accounts_root:
        acct_str = str(accounts_root)
        if Path(acct_str).is_absolute() or PureWindowsPath(acct_str).is_absolute():
            accounts_path = Path(acct_str).expanduser()
        else:
            accounts_path = (repo_path / acct_str).resolve()
        data_root = accounts_path.parent
    else:
        accounts_path = data_root / "accounts"

    virtual_root = data_root / "virtual_portfolios"
    return ResolvedPaths(repo_path, accounts_path, virtual_root)


# For future AWS use
DATA_BUCKET_ENV = "DATA_BUCKET"
PLOTS_PREFIX = "accounts/"


# ------------------------------------------------------------------
# Local discovery
# ------------------------------------------------------------------
_METADATA_STEMS = {"person", "config", "notes"}  # ignore these as accounts
_SKIP_OWNERS = {".idea", "demo"}


def _list_local_plots(
    data_root: Optional[Path] = None,
    current_user: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List available plots from the local filesystem.

    Parameters
    ----------
    data_root:
        Optional base directory containing account data. If ``None`` the
        configured accounts root is used.
    current_user:
        Username of the authenticated user or ``None`` when unauthenticated.
    """

    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = data_root or paths.accounts_root
    results: List[Dict[str, Any]] = []
    if not root.exists():
        return results

    # ``current_user`` may be passed in as ``None``, a simple string identifier
    # or as a ``ContextVar`` (mirroring the AWS loader).  Normalise the value to
    # the underlying string before applying permission checks.
    user = current_user.get(None) if hasattr(current_user, "get") else current_user

    for owner_dir in sorted(root.iterdir()):
        if not owner_dir.is_dir():
            continue
        if owner_dir.name in _SKIP_OWNERS:
            continue
        # When authentication is enabled (``disable_auth`` is explicitly
        # ``False``) and no user is authenticated, do not expose any accounts.
        # ``config.disable_auth`` defaults to ``None`` when the configuration
        # file cannot be loaded, which previously triggered this condition
        # unintentionally.  Be explicit about the check so that a missing config
        # behaves the same as auth being disabled.
        if config.disable_auth is False and user is None:
            continue

        owner = owner_dir.name
        meta = load_person_meta(owner, root)
        viewers = meta.get("viewers", [])
        if user and user != owner and user not in viewers:
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

        results.append({"owner": owner, "accounts": dedup})

    return results


# ------------------------------------------------------------------
# AWS discovery
# ------------------------------------------------------------------
def _list_aws_plots(current_user: Optional[str] = None) -> List[Dict[str, Any]]:
    """List available plots from an S3 bucket.

    Parameters
    ----------
    current_user:
        Username of the authenticated user or ``None`` when unauthenticated.

    The bucket name is read from the ``DATA_BUCKET`` environment variable and
    objects are expected under ``accounts/<owner>/<account>.json``. Metadata
    files like ``person.json`` are ignored and account names are de-duplicated
    case-insensitively. When authentication is enabled and no user is
    authenticated, no owners are exposed, mirroring the behaviour of the local
    loader.
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

    for skip_owner in _SKIP_OWNERS:
        owners.pop(skip_owner, None)

    user = current_user.get(None) if hasattr(current_user, "get") else current_user
    results: List[Dict[str, Any]] = []
    for owner, accounts in sorted(owners.items()):
        # When authentication is enabled (``disable_auth`` explicitly ``False``)
        # and no user is authenticated, do not expose any accounts.  If the
        # configuration failed to load ``disable_auth`` will be ``None``;
        # treating that as "auth disabled" avoids filtering everything.
        if (
            config.disable_auth is False
            and current_user is None
        ):
            continue
        if current_user and current_user != owner:
            meta = load_person_meta(owner)
            viewers = meta.get("viewers", [])
            if user not in viewers:
                continue
        results.append({"owner": owner, "accounts": accounts})
    return results


# ------------------------------------------------------------------
# Public discovery API
# ------------------------------------------------------------------
def list_plots(
    data_root: Optional[Path] = None,
    current_user: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Public helper to list available account plots.

    Parameters
    ----------
    data_root:
        Optional base directory containing account data when running locally.
    current_user:
        Username of the authenticated user or ``None`` if unauthenticated.

    Returns
    -------
    List[Dict[str, Any]]
        A list of dictionaries each containing an ``owner`` and their
        available ``accounts``.
    """

    if config.app_env == "aws":
        return _list_aws_plots(current_user)
    return _list_local_plots(data_root, current_user)


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
def load_account(
    owner: str,
    account: str,
    data_root: Optional[Path] = None,
) -> Dict[str, Any]:
    if config.app_env == "aws":
        bucket = os.getenv(DATA_BUCKET_ENV)
        if not bucket:
            raise FileNotFoundError(f"Missing {DATA_BUCKET_ENV} env var for AWS account loading")
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
        data = json.loads(txt)
        return data

    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = data_root or paths.accounts_root
    path = root / owner / f"{account}.json"
    data = _safe_json_load(path)
    return data


def load_person_meta(owner: str, data_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load per-owner metadata including optional email.

    Returns an empty dict if no metadata exists or parsing fails.
    """

    def _extract(data: Dict[str, Any]) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        for key in ("dob", "email", "holdings", "viewers"):
            if key in data:
                meta[key] = data[key]
        if "viewers" not in meta:
          # Preserve account access viewers if present
          meta["viewers"] = data.get("viewers", [])
        return meta

    if config.app_env == "aws" or os.getenv(DATA_BUCKET_ENV):
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
            data = json.loads(txt)
            return _extract(data)
        except Exception:
            return {}
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = data_root or paths.accounts_root
    path = root / owner / "person.json"
    if not path.exists():
        return {}
    try:
        data = _safe_json_load(path)
    except Exception:
        return {}
    return _extract(data)


# ------------------------------------------------------------------
# Virtual portfolio helpers
# ------------------------------------------------------------------


def _virtual_portfolio_path(name: str, root: Optional[Path] = None) -> Path:
    paths = resolve_paths(config.repo_root, config.accounts_root)
    vf_root = root or paths.virtual_pf_root
    return vf_root / f"{name}.json"


def list_virtual_portfolios(root: Optional[Path] = None) -> list[str]:
    paths = resolve_paths(config.repo_root, config.accounts_root)
    vf_root = root or paths.virtual_pf_root
    if not vf_root.exists():
        return []
    return sorted(p.stem for p in vf_root.glob("*.json"))


def load_virtual_portfolio(name: str, root: Optional[Path] = None) -> VirtualPortfolio:
    path = _virtual_portfolio_path(name, root)
    data = _safe_json_load(path)
    return VirtualPortfolio.model_validate(data)


def save_virtual_portfolio(pf: VirtualPortfolio, root: Optional[Path] = None) -> None:
    paths = resolve_paths(config.repo_root, config.accounts_root)
    vf_root = root or paths.virtual_pf_root
    vf_root.mkdir(parents=True, exist_ok=True)
    path = vf_root / f"{pf.name}.json"
    path.write_text(pf.model_dump_json(indent=2))
