#!/usr/bin/env python3
"""Guard against slug collisions before `aws s3 sync data/accounts` deploys.

`derive_owner_slug`/`provision_owner` (backend/common/signup_provision.py)
never let live signups overwrite a different owner's directory, but the
manual `aws s3 sync data/accounts s3://$DATA_BUCKET/accounts/` deploy step
(see docs/DEPLOY.md) bypasses that entirely: `aws s3 sync` has no notion of
slug ownership and will silently overwrite any object at a matching key.

This script compares each local `data/accounts/<slug>/person.json` email
against the same key already in the target bucket. A slug present in both
places with a *different* email is a collision and aborts the sync; a slug
that is new, or belongs to the same owner, is left alone. See #4796.

Usage:
    python scripts/check_account_slug_collisions.py --bucket my-data-bucket \
        [--accounts-dir data/accounts] [--prefix accounts/]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class Collision:
    def __init__(self, slug: str, local_email: str, remote_email: str) -> None:
        self.slug = slug
        self.local_email = local_email
        self.remote_email = remote_email

    def __str__(self) -> str:
        return (
            f"slug '{self.slug}': local owner ({self.local_email or '<no email>'}) "
            f"!= existing S3 owner ({self.remote_email or '<no email>'})"
        )


def local_slugs(accounts_dir: Path) -> list[str]:
    """Return the owner slugs present as subdirectories of `accounts_dir`."""
    if not accounts_dir.is_dir():
        return []
    return sorted(p.name for p in accounts_dir.iterdir() if p.is_dir())


def _read_local_email(accounts_dir: Path, slug: str) -> str:
    person_path = accounts_dir / slug / "person.json"
    try:
        data = json.loads(person_path.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    email = data.get("email") if isinstance(data, dict) else None
    return email.strip().lower() if isinstance(email, str) else ""


def remote_slugs(s3_client, bucket: str, prefix: str) -> set[str]:
    """Return the owner slugs already present under `prefix` in `bucket`.

    Uses a delimited (non-recursive) listing so this stays a cheap "which
    slugs exist" call rather than a full bucket scan.
    """
    normalized_prefix = prefix if prefix.endswith("/") or not prefix else f"{prefix}/"
    slugs: set[str] = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=normalized_prefix, Delimiter="/"):
        for entry in page.get("CommonPrefixes", []):
            key_prefix = entry["Prefix"]
            slug = key_prefix[len(normalized_prefix) :].rstrip("/")
            if slug:
                slugs.add(slug)
    return slugs


def _read_remote_email(s3_client, bucket: str, prefix: str, slug: str) -> str:
    key = f"{prefix.rstrip('/')}/{slug}/person.json" if prefix else f"{slug}/person.json"
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        data = json.loads(obj["Body"].read())
    except (ClientError, BotoCoreError, json.JSONDecodeError, OSError):
        return ""
    email = data.get("email") if isinstance(data, dict) else None
    return email.strip().lower() if isinstance(email, str) else ""


def find_collisions(
    accounts_dir: Path,
    s3_client,
    bucket: str,
    prefix: str,
    slugs: Iterable[str] | None = None,
) -> list[Collision]:
    """Return collisions between local and remote slugs with different owners.

    A slug counts as a collision only when both sides have a slug directory
    *and* their `person.json` emails disagree; a slug missing on either side,
    or matching on email, is not a collision.
    """
    candidate_slugs = list(slugs) if slugs is not None else local_slugs(accounts_dir)
    existing_remote = remote_slugs(s3_client, bucket, prefix)

    collisions: list[Collision] = []
    for slug in candidate_slugs:
        if slug not in existing_remote:
            continue
        local_email = _read_local_email(accounts_dir, slug)
        remote_email = _read_remote_email(s3_client, bucket, prefix, slug)
        if local_email and remote_email and local_email != remote_email:
            collisions.append(Collision(slug, local_email, remote_email))
    return collisions


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True, help="Target S3 bucket (DATA_BUCKET)")
    parser.add_argument(
        "--accounts-dir",
        default="data/accounts",
        type=Path,
        help="Local accounts directory (default: data/accounts)",
    )
    parser.add_argument(
        "--prefix",
        default="accounts/",
        help="S3 key prefix for accounts (default: accounts/)",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region to use (default: boto3's standard resolution order)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="AWS named profile to use (default: boto3's standard resolution order)",
    )
    args = parser.parse_args(argv[1:])

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3_client = session.client("s3")
    collisions = find_collisions(args.accounts_dir, s3_client, args.bucket, args.prefix)

    if collisions:
        print(
            "ERROR: refusing to sync — the following local account slugs "
            "collide with a different owner already in S3:",
            file=sys.stderr,
        )
        for collision in collisions:
            print(f"  - {collision}", file=sys.stderr)
        print(
            "Resolve the collision manually (rename the local slug or confirm "
            "the S3 owner) before running `aws s3 sync`.",
            file=sys.stderr,
        )
        return 1

    print("No account slug collisions found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
