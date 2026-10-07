"""Check and update this repo's pinned cicaid versions (#6597).

Ported from leonarduk/issue-worm's script of the same name (minus its
ollama-tools / aider-only pin, which allotmint does not use). Two
dependencies are tracked, each pinned in two places that must agree:

- cicaid-devtools -- the public leonarduk/cicaid "free shell". Pinned as a
  git+https URL in ``requirements-automation.txt`` and as ``CICAID_REF`` in
  ``.github/cicaid-pins.env``. "latest" comes from the GitHub Releases API,
  no token needed since the repo is public.
- cicaid-devtools-pro -- the private leonarduk/cicaid-pro, which carries the
  review modules ``.github/scripts/*_review.py`` import (review_common,
  deepseek_review, gpt_review, verdict, followup_issues). Pinned as a
  git+https URL in ``requirements-automation.txt`` and as ``CICAID_PRO_REF``
  in ``.github/cicaid-pins.env``. "latest" comes from the GitHub Releases
  API, which needs GITHUB_TOKEN since cicaid-pro is private.

The review workflow's pins live in the pins file rather than inline in
``.github/workflows/_ai-pr-review.yml`` because GitHub hard-blocks a
workflow's default GITHUB_TOKEN from pushing any change under
``.github/workflows/``, whatever permissions the job is granted -- so this
script could rewrite an inline pin but the update run could never push it.

Every file that pins a dependency must agree on the version, so
``current_pin`` treats disagreement as an error rather than picking one.

Stdlib-only by design: this script must run even when the pins are stale or
broken, so it must not import cicaid-devtools or any other project module.
The scheduled workflow (.github/workflows/update-dependencies.yml) uses
``--check`` to decide whether to open an update PR, then runs the script
again without ``--check`` on its own branch to rewrite the pins.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Pinned files are named with forward slashes throughout: the names appear
# verbatim in this script's output. _path joins them against the repo root
# in a platform-correct way.
REQUIREMENTS = "requirements-automation.txt"
CICAID_PINS = ".github/cicaid-pins.env"

DEPS = ("cicaid-devtools", "cicaid-devtools-pro")

CICAID_FREE_RELEASES_API = "https://api.github.com/repos/leonarduk/cicaid/releases/latest"
CICAID_PRO_RELEASES_API = "https://api.github.com/repos/leonarduk/cicaid-pro/releases/latest"

# Each dependency is pinned in two syntaxes: a git+https URL in
# requirements-automation.txt, and a KEY=<ref> line in the pins file. The
# pins-file ref is either a v-prefixed version tag or the literal "main".
# One alternation per dependency keeps a single pattern per spec (and so the
# cross-file drift check). MULTILINE makes the "^" in the pins-file branch
# anchor per line, so a commented-out pin is never read as a real one.
#
# The negative lookahead on cicaid-devtools' URL branch keeps it from also
# matching the cicaid-pro URL -- both share a "cicaid" prefix. Its pins-file
# branch needs no such guard: "^CICAID_REF=" cannot match CICAID_PRO_REF.
#
# "main" carries a (?=\r?$) of its own so it cannot match the "main" prefix
# of e.g. "mainline" (which would be rewritten to "v0.9.0line" instead of
# raising PinError). The optional "\r" tolerates a CRLF pins file. It is its
# own alternative ahead of the version form because "main" also matches
# [A-Za-z0-9.+-]*, and the engine would not come back to try it as "main".
#
# The groups are always the same three, so _rewrite can index them without
# knowing which dependency it is handling: group 1 is the prefix (a URL's
# "@v", or a KEY=), group 2 is a "v" after that prefix (only a pins-file tag
# has one) and group 3 is the value itself -- "main" or a bare version.
_CICAID_FREE_PIN_RE = re.compile(
    r"(git\+https://github\.com/leonarduk/cicaid(?!-pro)\.git@v"
    r"|^CICAID_REF=)"
    r"(v?)"
    r"(main(?=\r?$)|[0-9][A-Za-z0-9.+-]*)",
    re.MULTILINE,
)
_CICAID_PRO_PIN_RE = re.compile(
    r"(git\+https://github\.com/leonarduk/cicaid-pro\.git@v"
    r"|^CICAID_PRO_REF=)"
    r"(v?)"
    r"(main(?=\r?$)|[0-9][A-Za-z0-9.+-]*)",
    re.MULTILINE,
)


@dataclass(frozen=True)
class _Spec:
    """Where a dependency is pinned, and where its latest version comes from."""

    pin_re: re.Pattern
    releases_api: str
    # cicaid-pro is private: its releases API call needs GITHUB_TOKEN,
    # unlike the public cicaid repo.
    needs_token: bool
    files: tuple[str, ...]
    repo_slug: str
    pins_key: str


_SPECS = {
    "cicaid-devtools": _Spec(
        pin_re=_CICAID_FREE_PIN_RE,
        releases_api=CICAID_FREE_RELEASES_API,
        needs_token=False,
        files=(REQUIREMENTS, CICAID_PINS),
        repo_slug="cicaid",
        pins_key="CICAID_REF",
    ),
    "cicaid-devtools-pro": _Spec(
        pin_re=_CICAID_PRO_PIN_RE,
        releases_api=CICAID_PRO_RELEASES_API,
        needs_token=True,
        files=(REQUIREMENTS, CICAID_PINS),
        repo_slug="cicaid-pro",
        pins_key="CICAID_PRO_REF",
    ),
}

_USER_AGENT = "allotmint-update-dependency-pins"


class PinError(Exception):
    """A pin is missing, drifted, or could not be checked."""


def _spec(dep: str) -> _Spec:
    try:
        return _SPECS[dep]
    except KeyError:
        raise PinError(f"unknown dependency {dep!r} (expected one of {', '.join(DEPS)})") from None


def _path(root: Path, name: str) -> Path:
    return root.joinpath(*name.split("/"))


def _read_text(path: Path) -> str:
    # newline="" keeps \r\n intact instead of normalizing to \n (and on
    # write, back again), so a CRLF file survives a rewrite byte-for-byte
    # and the update PR diff stays clean.
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _http_json(url: str, token: str | None = None) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        # OSError covers URLError/HTTPError/timeouts; ValueError covers
        # JSONDecodeError. Any of these means the version is uncheckable.
        raise PinError(f"failed to fetch {url}: {exc}") from exc


def latest_version(dep: str, token: str | None = None) -> str:
    """Latest released version of ``dep`` (never a v-prefixed string)."""
    spec = _spec(dep)
    if spec.needs_token and not token:
        # GitHub answers an unauthenticated request for a private repo with
        # 404, which is indistinguishable from "no releases yet" -- say what
        # is actually wrong instead of letting that surface as a fetch error.
        raise PinError(
            f"{dep} lives in the private leonarduk/{spec.repo_slug}: checking it "
            "needs GITHUB_TOKEN set to a PAT with read access there (the workflow "
            "passes the CICAID_PRO_TOKEN secret)"
        )
    try:
        data = _http_json(spec.releases_api, token=token if spec.needs_token else None)
    except PinError as exc:
        if spec.needs_token:
            raise PinError(
                f"{exc} - for the private leonarduk/{spec.repo_slug} a 404 usually "
                "means the token has expired or lost read access to that repo"
            ) from exc
        raise
    tag = data.get("tag_name", "")
    if not tag.startswith("v"):
        raise PinError(f"unexpected {dep} release tag {tag!r}; expected a v-prefixed tag")
    return tag[1:]


# A release string we can reason about semantically: dotted numeric
# components, then an optional suffix (a pre-release like "rc1", or a
# PEP 440 local version like "+abc123").
_VERSION_RE = re.compile(r"^(\d+(?:\.\d+)*)(.*)$")


def _parse_version(version: str) -> tuple[tuple[int, ...], str] | None:
    """Split ``version`` into (release components, suffix), or None.

    Trailing zero components are dropped so ``1.0`` and ``1.0.0`` parse
    identically. Returns None for anything that does not start with a dotted
    numeric release, so callers can fall back to string comparison.
    """
    match = _VERSION_RE.match(version.strip())
    if match is None:
        return None
    release = [int(part) for part in match.group(1).split(".")]
    while release and release[-1] == 0:
        release.pop()
    # Suffixes compare case-insensitively, matching PEP 440 normalization.
    return tuple(release), match.group(2).strip().lower()


def _versions_equal(left: str, right: str) -> bool:
    """True when two version strings name the same release.

    Exact string equality reports ``1.0`` and ``1.0.0`` as different and
    would open a pointless update PR every day. Any suffix stays significant
    so a pre-release is never mistaken for its final release. Versions this
    cannot parse fall back to string equality.
    """
    parsed_left = _parse_version(left)
    parsed_right = _parse_version(right)
    if parsed_left is None or parsed_right is None:
        return left == right
    return parsed_left == parsed_right


def current_pin(dep: str, root: Path | None = None) -> str:
    """Currently pinned version of ``dep``, raising PinError on drift/gaps."""
    if root is None:
        root = ROOT
    spec = _spec(dep)
    found: dict[str, str] = {}
    for name in spec.files:
        match = spec.pin_re.search(_read_text(_path(root, name)))
        if match is None:
            raise PinError(f"no {dep} pin found in {name}")
        found[name] = match.group(3)
    if len(set(found.values())) > 1:
        detail = ", ".join(f"{name} has v{version}" for name, version in found.items())
        raise PinError(f"{dep} pins drifted: {detail}")
    return found[spec.files[0]]


def _rewrite(dep: str, text: str, new_version: str) -> str:
    spec = _spec(dep)

    def replace(match: re.Match) -> str:
        # Group 1 + group 2 rebuilds the "v"-carrying prefix a version is
        # written after. "main" is the one value with no "v" there, so it
        # needs one prepended to produce "KEY=v<version>".
        if match.group(3) == "main":
            return f"{match.group(1)}v{new_version}"
        return f"{match.group(1)}{match.group(2)}{new_version}"

    new_text, count = spec.pin_re.subn(replace, text)
    if count == 0:
        raise PinError(
            f"could not find the {dep} pin in the file (expected "
            f"git+https://github.com/leonarduk/{spec.repo_slug}.git@vX.Y.Z, "
            f"or a {spec.pins_key}=vX.Y.Z line in {CICAID_PINS})"
        )
    return new_text


def apply_update(dep: str, new_version: str, root: Path | None = None, dry_run: bool = False) -> list[str]:
    """Rewrite every pin for ``dep`` to ``new_version``.

    Returns the names of the files that would change; an already-pinned
    version is a no-op returning an empty list. Nothing is written when
    ``dry_run`` is true.
    """
    if root is None:
        root = ROOT
    changed: list[str] = []
    for name in _spec(dep).files:
        path = _path(root, name)
        text = _read_text(path)
        new_text = _rewrite(dep, text, new_version)
        if new_text != text:
            if not dry_run:
                _write_text(path, new_text)
            changed.append(name)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check/update the pinned cicaid-devtools[-pro] versions.")
    parser.add_argument("dependency", choices=DEPS)
    parser.add_argument(
        "--check",
        action="store_true",
        help="only report whether an update exists; never writes files",
    )
    parser.add_argument("--dry-run", action="store_true", help="print what would change without writing")
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN")
    try:
        new_version = latest_version(args.dependency, token=token)
        current = current_pin(args.dependency)
    except PinError as exc:
        print(f"update_dependency_pins: {exc}", file=sys.stderr)
        return 1

    if _versions_equal(new_version, current):
        print(f"UP-TO-DATE {args.dependency} {current}")
        return 0

    if args.check:
        print(f"UPDATE {args.dependency} {current} -> {new_version}")
        return 0

    try:
        changed = apply_update(args.dependency, new_version, dry_run=args.dry_run)
    except PinError as exc:
        print(f"update_dependency_pins: {exc}", file=sys.stderr)
        return 1

    verb = "WOULD UPDATE" if args.dry_run else "UPDATED"
    detail = ", ".join(changed) if changed else "no files (already up to date)"
    print(f"{verb} {args.dependency} {current} -> {new_version} ({detail})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
