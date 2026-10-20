"""Print the allotmint-pro release tag pinned by the ``pro`` extra.

The deploy workflow checks out allotmint-pro at this tag to build the wheel
baked into the Lambda image (#11004), so the image and ``pip install ".[pro]"``
always use the same release.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
_PIN = re.compile(r"^allotmint-pro @ git\+ssh://git@github\.com/leonarduk/allotmint-pro\.git@(v\d+\.\d+\.\d+)$")


def pinned_tag(pyproject: Path = PYPROJECT) -> str:
    """Return the ``vX.Y.Z`` tag from the single ``pro`` extra requirement."""
    with pyproject.open("rb") as handle:
        extras = tomllib.load(handle)["project"]["optional-dependencies"]["pro"]
    if len(extras) != 1:
        raise ValueError(f"expected exactly one requirement in the pro extra, got {extras!r}")
    match = _PIN.match(extras[0])
    if match is None:
        raise ValueError(f"pro extra is not pinned to a vX.Y.Z tag: {extras[0]!r}")
    return match.group(1)


if __name__ == "__main__":
    try:
        print(pinned_tag())
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
