from __future__ import annotations

"""Data loading helpers for AllotMint."""

import inspect
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List, Optional

from backend.common.virtual_portfolio import VirtualPortfolio
from backend.config import config, demo_identity as get_demo_identity


logger = logging.getLogger(__name__)


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
_METADATA_STEMS = {
    "person",
    "config",
    "notes",
    "settings",
    "approvals",
    "approval_requests",
    "pension-forecast",
    "pension_forecast",
}  # ignore these as accounts

_ACCOUNT_CANONICAL_UPPER = {
    "isa",
    "sipp",
    "gia",
    "jisa",
    "lisa",
}


def _canonicalise_account_variant(name: str) -> str:
    """Return the preferred casing for ``name`` when known."""

    lowered = name.lower()
    if lowered in _ACCOUNT_CANONICAL_UPPER:
        return lowered.upper()
    return name


def _normalise_local_account_name(name: str) -> str:
    """Normalise account names for local listings."""

    lowered = name.lower()
    if lowered in _ACCOUNT_CANONICAL_UPPER:
        return lowered
    return name


def demo_identity_aliases() -> List[str]:
    """Return configured demo identity aliases including the default."""

    aliases: List[str] = []
    seen: set[str] = set()
    for candidate in (get_demo_identity(), "demo"):
        if not isinstance(candidate, str):
            continue
        normalised = candidate.strip()
        if not normalised:
            continue
        lowered = normalised.lower()
        if lowered in seen:
            continue
        aliases.append(normalised)
        seen.add(lowered)
    if not aliases:
        aliases.append("demo")
    return aliases


def _skip_owners() -> set[str]:
    """Return owner identifiers that should be ignored when listing data."""

    skipped = {".idea"}
    for alias in demo_identity_aliases():
        skipped.add(alias.lower())
    return skipped


def _extract_account_names(owner_dir: Path) -> List[str]:
    """Return de-duplicated account names for ``owner_dir``."""

    def _score_variant(value: str) -> tuple[int, str]:
        """Return a score for ``value`` to prefer canonical capitalisation."""

        if value.isupper():
            return (3, value)
        if any(ch.isupper() for ch in value):
            return (2, value)
        return (1, value)

    acct_names: List[str] = []
    try:
        entries = sorted(owner_dir.iterdir())
    except OSError:
        entries = []

    for path in entries:
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        stem = path.stem
        lowered = stem.lower()
        if lowered in _METADATA_STEMS:
            continue
        if lowered.endswith("_transactions"):
            continue
        acct_names.append(stem)

    seen: dict[str, int] = {}
    dedup: List[str] = []
    for name in acct_names:
        lowered = name.lower()
        canonical = _canonicalise_account_variant(name)
        if lowered in seen:
            idx = seen[lowered]
            if _score_variant(canonical) > _score_variant(dedup[idx]):
                dedup[idx] = canonical
            continue
        seen[lowered] = len(dedup)
        dedup.append(canonical)
    return dedup


def _build_owner_summary(
    owner: str,
    accounts: List[str],
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Construct an owner summary including a display name."""

    summary: Dict[str, Any] = {"owner": owner, "accounts": accounts}

    display_name: Optional[str] = None
    if isinstance(meta, dict):
        for key in ("full_name", "display_name", "preferred_name", "owner", "name"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                display_name = value.strip()
                if key == "full_name":
                    break
    if display_name:
        summary["full_name"] = display_name

    return summary


def _load_demo_owner(root: Path) -> Optional[Dict[str, Any]]:
    """Return the bundled demo owner description if available."""

    base_root = (root or Path()).expanduser()

    for identity in demo_identity_aliases():
        try:
            demo_dir = base_root / identity
        except Exception:
            continue

        try:
            exists = demo_dir.exists() and demo_dir.is_dir()
        except Exception:
            continue

        if not exists:
            continue

        accounts = [
            _normalise_local_account_name(name)
            for name in _extract_account_names(demo_dir)
        ]
        meta = load_person_meta(identity, root)
        summary = _build_owner_summary(identity, accounts, meta)
        if summary:
            return summary

    return None


def _merge_accounts(base: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> None:
    """Merge account names from ``extra`` into ``base`` in-place."""

    if not base or not extra:
        return

    if "full_name" not in base:
        extra_name = extra.get("full_name")
        if isinstance(extra_name, str) and extra_name:
            base["full_name"] = extra_name

    existing = base.setdefault("accounts", [])
    if not isinstance(existing, list):
        return

    seen = {str(name).lower() for name in existing}
    for name in extra.get("accounts", []):
        if not isinstance(name, str):
            continue
        lowered = name.lower()
        if lowered in seen:
            continue
        existing.append(name)
        seen.add(lowered)


def _list_local_plots(
    data_root: Optional[Path] = None,
    current_user: Optional[str] = None,
    *,
    apply_default_full_name: bool = True,
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

    user = (
        current_user.get(None)
        if hasattr(current_user, "get")
        else current_user
    )

    demo_aliases = demo_identity_aliases()
    demo_identity = get_demo_identity()
    demo_lower = demo_identity.lower() if isinstance(demo_identity, str) else "demo"
    demo_lower_aliases = {alias.lower() for alias in demo_aliases}
    demo_lower = demo_aliases[0].lower() if demo_aliases else "demo"

    def _is_authorized(owner: str, meta: Dict[str, Any]) -> bool:
        viewers = meta.get("viewers", []) if isinstance(meta, dict) else []
        if not isinstance(viewers, list):
            viewers = []

        if config.disable_auth:
            if user is None:
                return True
            # Fall back to the identity checks below when a caller supplies a
            # specific user.  This allows local "disable_auth" environments to
            # emulate logged-in views and still respect per-account viewer
            # permissions.

        if config.disable_auth is False and user is None:
            return False

        if isinstance(user, str):
            allowed_identities = {owner.lower()}
            email = meta.get("email") if isinstance(meta, dict) else None
            if isinstance(email, str) and email:
                allowed_identities.add(email.lower())
            allowed_identities.update(
                v.lower() for v in viewers if isinstance(v, str)
            )
            return user.lower() in allowed_identities

        if user and user != owner and user not in viewers:
            return False

        return True

    def _discover(
        root: Path,
        *,
        include_demo: bool = False,
        apply_default_full_name_flag: bool = False,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not root.exists():
            return results

        skip_owners = _skip_owners()
        if include_demo:
            for alias in demo_identity_aliases():
                skip_owners.discard(alias.lower())

        for owner_dir in sorted(root.iterdir()):
            if not owner_dir.is_dir():
                continue
            if owner_dir.name in skip_owners:
                continue
            owner = owner_dir.name
            meta = load_person_meta(owner, root)
            if not _is_authorized(owner, meta):
                continue

            accounts = [
                _normalise_local_account_name(name)
                for name in _extract_account_names(owner_dir)
            ]

            summary = _build_owner_summary(owner, accounts, meta)

            if apply_default_full_name_flag and "full_name" not in summary:
                summary["full_name"] = owner


            results.append(summary)

        return results

    paths = resolve_paths(config.repo_root, config.accounts_root)
    primary_root = Path(data_root) if data_root else paths.accounts_root

    fallback_paths = resolve_paths(None, None)
    fallback_root = fallback_paths.accounts_root

    explicit_root = data_root is not None

    try:
        explicit_matches_fallback = (
            explicit_root
            and Path(data_root).expanduser().resolve() == fallback_root.resolve()
        )
    except Exception:
        explicit_matches_fallback = False

    try:
        explicit_matches_config = (
            explicit_root
            and getattr(config, "accounts_root", None)
            and Path(config.accounts_root).expanduser().resolve()
            == Path(data_root).expanduser().resolve()
        )
    except Exception:
        explicit_matches_config = False

    try:
        config_repo_matches_fallback = (
            getattr(config, "repo_root", None)
            and Path(config.repo_root).expanduser().resolve()
            == fallback_paths.repo_root.resolve()
        )
    except Exception:
        config_repo_matches_fallback = False

    explicit_is_global = explicit_matches_fallback or (
        explicit_matches_config and config_repo_matches_fallback
    )

    include_demo_primary = bool(config.disable_auth) and (
        not explicit_root or explicit_is_global
    )

    if not explicit_root and not include_demo_primary:
        try:
            include_demo_primary = primary_root.resolve() == fallback_root.resolve()
        except Exception:
            include_demo_primary = False

    default_primary_full_name = bool(
        apply_default_full_name
        and explicit_root
        and not explicit_is_global
        and not explicit_matches_config
    )

    results = _discover(
        primary_root,
        include_demo=False,
        apply_default_full_name_flag=default_primary_full_name,
    )

    if include_demo_primary and not results:
        results = _discover(
            primary_root,
            include_demo=True,
            apply_default_full_name_flag=default_primary_full_name,
        )

    try:
        same_root = fallback_root.resolve() == primary_root.resolve()
    except OSError:
        same_root = False

    # When an explicit ``data_root`` is provided treat it as authoritative and
    # avoid blending in accounts from the repository fallback tree.  This keeps
    # unit tests (which use temporary roots) isolated from the real repository
    # data and mirrors the expectation that callers passing a custom root only
    # see data from that location.
    if not explicit_root and not results:
        fallback_results = _discover(
            fallback_root,
            include_demo=False,
            apply_default_full_name_flag=apply_default_full_name,
        )
        if config.disable_auth and not fallback_results:
            fallback_results = _discover(
                fallback_root,
                include_demo=True,
                apply_default_full_name_flag=apply_default_full_name,
            )
        results.extend(fallback_results)

    owners_index = {
        str(entry.get("owner", "")).lower(): entry for entry in results
    }

    if explicit_root and not explicit_is_global:
        allow_fallback_demo = False
    else:
        allow_fallback_demo = bool(config.disable_auth) or not results

    has_non_demo_owner = any(
        owner and owner != demo_lower for owner in owners_index
    )
    demo_variant = f"{demo_lower}-owner"
    has_demo_variant = demo_variant in owners_index
    if has_demo_variant:
        suppress_demo = has_non_demo_owner
    else:
        suppress_demo = has_non_demo_owner and (
            (not explicit_root) or explicit_matches_fallback or (not allow_fallback_demo)
        )
    if not allow_fallback_demo and suppress_demo:
        return results

    def _attach_demo_from(root: Optional[Path]) -> bool:
        if not root:
            return False
        demo_entry = _load_demo_owner(root)
        if not demo_entry:
            return False
        owner_value = str(demo_entry.get("owner", "")).strip()
        if not owner_value:
            return False
        meta = load_person_meta(owner_value, root)
        if not _is_authorized(owner_value, meta):
            return False
        results.append(demo_entry)
        owners_index[owner_value.lower()] = demo_entry
        return True

    existing_demo_key = next(
        (alias for alias in demo_lower_aliases if alias in owners_index), None
    )

    if existing_demo_key:
        if allow_fallback_demo:
            fallback_demo = _load_demo_owner(fallback_root)
            if (
                fallback_demo
                and isinstance(fallback_demo.get("owner"), str)
                and fallback_demo["owner"].strip().lower() == existing_demo_key
            ):
                _merge_accounts(owners_index[existing_demo_key], fallback_demo)
    else:
        if allow_fallback_demo and config.disable_auth and not suppress_demo:
            if _attach_demo_from(fallback_root):
                allow_fallback_demo = False

        include_demo = config.disable_auth or include_demo_primary
        demo_missing = not any(
            alias in owners_index for alias in demo_lower_aliases
        )
        if include_demo and demo_missing and not suppress_demo:
            target_root: Optional[Path]
            if include_demo_primary:
                target_root = primary_root
            elif allow_fallback_demo:
                target_root = fallback_root
            else:
                target_root = None
            if target_root:
                _attach_demo_from(target_root)

    def _lookup_meta(owner: str) -> Dict[str, Any]:
        """Load metadata for ``owner`` from known search roots."""

        # Prefer the primary root so callers overriding ``data_root`` can
        # specify bespoke metadata for tests. Fall back to the repository data
        # directory if the owner does not exist in the primary location.
        for root in (primary_root, fallback_root):
            try:
                person_file = root / owner / "person.json"
            except TypeError:
                continue
            if person_file.exists():
                return load_person_meta(owner, root)
        return {}

    if same_root:
        filtered_results: List[Dict[str, Any]] = []
        for entry in results:
            owner = str(entry.get("owner", ""))
            if not owner:
                continue
            if _is_authorized(owner, _lookup_meta(owner)):
                filtered_results.append(entry)
        return filtered_results

    if (
        (include_demo_primary or allow_fallback_demo)
        and not any(alias in owners_index for alias in demo_lower_aliases)
        and demo_lower not in owners_index
        and config.disable_auth
        and not suppress_demo
    ):
        primary_demo = _load_demo_owner(primary_root)

        if primary_demo:
            owner_value = str(primary_demo.get("owner", "")).strip()
            if owner_value:
                primary_meta = load_person_meta(owner_value, primary_root)
                if _is_authorized(owner_value, primary_meta):
                    owners_index[owner_value.lower()] = primary_demo
                    results.append(primary_demo)

    filtered_results: List[Dict[str, Any]] = []
    for entry in results:
        owner = str(entry.get("owner", ""))
        if not owner:
            continue
        if not _is_authorized(owner, _lookup_meta(owner)):
            continue
        filtered_results.append(entry)

    return filtered_results


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

    for skip_owner in _skip_owners():
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
        meta = load_person_meta(owner)
        if current_user and current_user != owner:
            viewers = meta.get("viewers", [])
            if user not in viewers:
                continue
        results.append(_build_owner_summary(owner, accounts, meta))
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
        A list of dictionaries each containing an ``owner`` identifier, a
        human-friendly ``full_name`` (if available) and their available
        ``accounts``.
    """

    if config.app_env == "aws":
        aws_results = _list_aws_plots(current_user)
        if data_root is None or aws_results:
            return aws_results
        local_loader = _list_local_plots
        try:
            params = inspect.signature(local_loader).parameters
        except (TypeError, ValueError):  # pragma: no cover - defensive
            params = {}
        if "apply_default_full_name" in params:
            return local_loader(
                data_root,
                current_user,
                apply_default_full_name=False,
            )
        return local_loader(data_root, current_user)

    local_loader = _list_local_plots
    try:
        params = inspect.signature(local_loader).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        params = {}
    if "apply_default_full_name" in params:
        return local_loader(
            data_root,
            current_user,
            apply_default_full_name=False,
        )
    return local_loader(data_root, current_user)


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
    bucket = os.getenv(DATA_BUCKET_ENV)

    if config.app_env == "aws":
        if not bucket:
            raise FileNotFoundError(
                f"Missing {DATA_BUCKET_ENV} env var for AWS account loading"
            )

    local_root: Optional[Path] = data_root
    if local_root is None:
        try:
            local_root = resolve_paths(config.repo_root, config.accounts_root).accounts_root
        except Exception:  # pragma: no cover - extremely defensive
            local_root = None

    if config.app_env == "aws":
        if bucket:
            key = f"{PLOTS_PREFIX}{owner}/{account}.json"
            try:
                import boto3  # type: ignore

                obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
            except Exception as exc:
                logger.warning(
                    "Failed to load account data from s3://%s/%s: %s; falling back to local file",
                    bucket,
                    key,
                    exc,
                    exc_info=True,
                )
                if not local_root:
                    raise FileNotFoundError(f"s3://{bucket}/{key}") from exc
            else:
                body = obj.get("Body")
                txt = body.read().decode("utf-8-sig").strip() if body else ""
                if not txt:
                    raise ValueError(f"Empty JSON file: s3://{bucket}/{key}")
                data = json.loads(txt)
                return data

    if not local_root:
        raise FileNotFoundError(f"No account data available for owner '{owner}'")

    root = local_root
    path = root / owner / f"{account}.json"
    data = _safe_json_load(path)
    return data


def load_person_meta(owner: str, data_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load per-owner metadata including optional email.

    Returns an empty dict if no metadata exists or parsing fails.
    """

    def _extract(data: Dict[str, Any]) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        allowed_keys = {
            "owner",
            "full_name",
            "display_name",
            "preferred_name",
            "dob",
            "email",
            "holdings",
            "viewers",
        }
        for key in allowed_keys:
            if key in data:
                meta[key] = data[key]
        if "viewers" not in meta:
            # Preserve account access viewers if present
            meta["viewers"] = data.get("viewers", [])
        return meta

    local_root: Optional[Path] = data_root
    if local_root is None:
        try:
            local_root = resolve_paths(config.repo_root, config.accounts_root).accounts_root
        except Exception:  # pragma: no cover - extremely defensive
            local_root = None

    has_local_fallback = local_root is not None
    bucket = os.getenv(DATA_BUCKET_ENV)

    if config.app_env == "aws" or bucket:
        if bucket:
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
            except Exception as exc:
                logger.warning(
                    "Failed to load person metadata from s3://%s/%s: %s; falling back to local file",
                    bucket,
                    key,
                    exc,
                    exc_info=True,
                )
                if config.app_env == "aws" and not has_local_fallback:
                    return {}
        elif config.app_env == "aws" and not has_local_fallback:
            return {}

    if not local_root:
        return {}

    root = local_root
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
