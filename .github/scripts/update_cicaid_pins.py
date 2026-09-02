"""Check and update the cicaid pins in the repo's cicaid-pins.env.

Scaffolded by `cicaid setup-review-actions` and driven by
.github/workflows/update-cicaid.yml on a schedule. Re-running
setup-review-actions overwrites this file, so edit the generator
(cicaid-pro's setup_review_actions.py) rather than this copy.

Stdlib-only by design: this must run even when the pin it is fixing is
stale or malformed, so it cannot import cicaid_devtools -- the package that
very pin installs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PINS_PATH = ".github/cicaid-pins.env"

# The only pin shapes accepted, matching the validation the workflow's own
# install step applies: a released tag, or the literal "main" the scaffolder
# falls back to when the releases lookup fails at setup time. A "main" pin
# never compares equal to a release, so the first scheduled run after such a
# fallback pins a real version -- the repo self-heals.
_PIN_VALUE = r"(?:main|v[0-9][A-Za-z0-9.+-]*)"

# dep -> (pins-file key, latest-release API, needs an auth token to read it).
# leonarduk/cicaid is public; leonarduk/cicaid-pro is private, so its lookup
# 404s unauthenticated and reuses the CICAID_PRO_TOKEN secret this repo
# already needs to install it (a fine-grained PAT with Contents: Read-only,
# which covers the releases API).
_DEPS = {
    "cicaid-devtools": (
        "CICAID_REF",
        "https://api.github.com/repos/leonarduk/cicaid/releases/latest",
        False,
    ),
    "cicaid-devtools-pro": (
        "CICAID_PRO_REF",
        "https://api.github.com/repos/leonarduk/cicaid-pro/releases/latest",
        True,
    ),
}

_USER_AGENT = "cicaid-update-cicaid-pins"


class PinError(Exception):
    """A pin is missing, malformed, or could not be checked."""


def _pin_re(key: str) -> re.Pattern[str]:
    """Match ``KEY=<pin>`` on its own line, with the pin as group 2.

    The optional carriage return tolerates a CRLF pins file: the scaffolder
    writes it with the setup machine's line endings, so a setup run on
    Windows commits CRLF, and a bare end-of-line anchor would then never
    match on the Linux runner.
    """
    return re.compile(
        r"^(" + re.escape(key) + r"=)(" + _PIN_VALUE + r")\r?$", re.MULTILINE
    )


def _read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_text(path: Path, text: str) -> None:
    # newline="" so rewriting one pin does not also rewrite every line
    # ending in the file, which would bury the change in the diff.
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
        raise PinError(f"failed to fetch {url}: {exc}") from exc


def latest_version(dep: str, token: str | None = None) -> str:
    """Latest released version of ``dep``, never v-prefixed."""
    _key, releases_api, needs_token = _DEPS[dep]
    if needs_token and not token:
        raise PinError(
            f"{dep} lives in a private repo; set GITHUB_TOKEN to a token that "
            "can read its releases (the CICAID_PRO_TOKEN secret)"
        )
    data = _http_json(releases_api, token=token if needs_token else None)
    tag = data.get("tag_name", "")
    if not tag.startswith("v"):
        raise PinError(f"unexpected {dep} release tag {tag!r}; expected a v-prefixed tag")
    return tag[1:]


_VERSION_RE = re.compile(r"^(\d+(?:\.\d+)*)(.*)$")


def _parse_version(version: str) -> tuple[tuple[int, ...], str] | None:
    """Split into (release components, suffix), or None if not numeric-led.

    Trailing zero components are dropped so 1.0 and 1.0.0 parse identically.
    """
    match = _VERSION_RE.match(version.strip())
    if match is None:
        return None
    release = [int(part) for part in match.group(1).split(".")]
    while release and release[-1] == 0:
        release.pop()
    return tuple(release), match.group(2).strip().lower()


def _versions_equal(left: str, right: str) -> bool:
    """True when two version strings name the same release.

    String equality alone would call 1.0 and 1.0.0 different and open a
    pointless update PR every single day.
    """
    parsed_left = _parse_version(left)
    parsed_right = _parse_version(right)
    if parsed_left is None or parsed_right is None:
        return left == right
    return parsed_left == parsed_right


def current_pin(dep: str, root: Path | None = None) -> str:
    """Currently pinned version of ``dep`` (v-prefix stripped), or "main"."""
    root = ROOT if root is None else root
    key = _DEPS[dep][0]
    match = _pin_re(key).search(_read_text(root / PINS_PATH))
    if match is None:
        raise PinError(f"no valid {key}=<pin> line in {PINS_PATH}")
    value = match.group(2)
    return value if value == "main" else value[1:]


def apply_update(
    dep: str, new_version: str, root: Path | None = None, dry_run: bool = False
) -> bool:
    """Rewrite ``dep``'s pin to ``new_version``. True if the file changed."""
    root = ROOT if root is None else root
    key = _DEPS[dep][0]
    path = root / PINS_PATH
    text = _read_text(path)
    match = _pin_re(key).search(text)
    if match is None:
        raise PinError(f"no valid {key}=<pin> line in {PINS_PATH}")
    start, end = match.span(2)
    new_text = text[:start] + "v" + new_version + text[end:]
    if new_text == text:
        return False
    if not dry_run:
        _write_text(path, new_text)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check/update the cicaid-devtools and cicaid-devtools-pro pins."
    )
    parser.add_argument("dependency", choices=sorted(_DEPS))
    parser.add_argument(
        "--check",
        action="store_true",
        help="only report whether an update exists; never writes files",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would change without writing"
    )
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN")
    try:
        new_version = latest_version(args.dependency, token=token)
        current = current_pin(args.dependency)
    except PinError as exc:
        print(f"update_cicaid_pins: {exc}", file=sys.stderr)
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
        print(f"update_cicaid_pins: {exc}", file=sys.stderr)
        return 1

    verb = "WOULD UPDATE" if args.dry_run else "UPDATED"
    detail = PINS_PATH if changed else "no files (already up to date)"
    print(f"{verb} {args.dependency} {current} -> {new_version} ({detail})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
