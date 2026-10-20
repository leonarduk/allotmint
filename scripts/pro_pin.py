"""Print the allotmint-pro release pinned by the ``pro`` extra.

The deploy workflow checks out allotmint-pro at this tag to build the wheel
baked into the Lambda image (#11004), so the image and ``pip install ".[pro]"``
always use the same release. ``--requirement`` prints the whole requirement
instead, for local deploys that build the wheel over SSH
(``pip wheel --no-deps --wheel-dir pro_wheels "<requirement>"``).
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
_PIN = re.compile(r"^allotmint-pro @ git\+ssh://git@github\.com/leonarduk/allotmint-pro\.git@(v\d+\.\d+\.\d+)$")


def pinned_requirement(pyproject: Path = PYPROJECT) -> str:
    """Return the single ``pro`` extra requirement, checked to pin a ``vX.Y.Z`` tag."""
    with pyproject.open("rb") as handle:
        extras = tomllib.load(handle)["project"]["optional-dependencies"]["pro"]
    if len(extras) != 1:
        raise ValueError(f"expected exactly one requirement in the pro extra, got {extras!r}")
    if _PIN.match(extras[0]) is None:
        raise ValueError(f"pro extra is not pinned to a vX.Y.Z tag: {extras[0]!r}")
    return extras[0]


def pinned_tag(pyproject: Path = PYPROJECT) -> str:
    """Return the ``vX.Y.Z`` tag from the single ``pro`` extra requirement."""
    return _PIN.match(pinned_requirement(pyproject)).group(1)


if __name__ == "__main__":
    try:
        print(pinned_requirement() if "--requirement" in sys.argv[1:] else pinned_tag())
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
