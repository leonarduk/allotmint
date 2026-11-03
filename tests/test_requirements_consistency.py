"""Regression tests keeping root and backend requirements files in sync (issue #6016).

`scripts/run-backend.ps1` and `scripts/bash/run-local-api.sh` install dependencies
from the root `requirements.txt`, not `backend/requirements.txt`. If a package that
`backend/` actually imports is only pinned in `backend/requirements.txt`, a fresh
local venv built from the root file will be missing it and the backend will crash
at import time (e.g. `ModuleNotFoundError: No module named 'jinja2'`).
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_REQUIREMENTS = REPO_ROOT / "requirements.txt"
BACKEND_REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"

# The two sides whose shared ``~=`` pins must agree (#11386). Dependabot bumps
# both in one PR (.github/dependabot.yml: one pip entry for "/" and "/backend"
# with ``group-by: dependency-name``), so equal pins stay equal.
ROOT_PIN_FILES = (ROOT_REQUIREMENTS, REPO_ROOT / "requirements-dev.txt")
BACKEND_PIN_FILES = (BACKEND_REQUIREMENTS, REPO_ROOT / "backend" / "requirements-test.txt")

# Packages that are legitimately backend-only build/deploy tooling and are not
# imported by backend/**/*.py at runtime, so they don't need to be mirrored
# into the root requirements.txt used by the local dev server.
BACKEND_ONLY_ALLOWLIST = {"setuptools"}

# Keep exemptions explicit and narrowly limited to packages that are genuinely
# needed only by local tooling. Runtime dependencies belong in both files so
# local development and Lambda/Docker deployments install the same package set.
ROOT_ONLY_ALLOWLIST: set[str] = set()

_PACKAGE_NAME_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")
# name, optional [extras], then the specifier up to an environment marker.
_REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*([^;]*)")


def _parse_package_names(path: Path) -> set[str]:
    names = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = _PACKAGE_NAME_RE.match(line)
        if match:
            names.add(match.group(1).lower())
    return names


def _normalise_name(name: str) -> str:
    """PEP 503 form: lowercase, runs of ``-``, ``_`` and ``.`` folded to ``-``."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _tilde_pins(paths: tuple[Path, ...]) -> dict[str, dict[str, list[str]]]:
    """Every ``~=`` pin in ``paths``: normalised name -> specifier -> files that use it.

    The specifier is compared with whitespace removed. ``>=``, ``==`` and
    unpinned requirements are left out (#11386 checks ``~=`` pins only).
    """
    pins: dict[str, dict[str, list[str]]] = {}
    for path in paths:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            match = _REQUIREMENT_RE.match(line)
            if not match:
                continue
            specifier = re.sub(r"\s+", "", match.group(2))
            if specifier.startswith("~="):
                files = pins.setdefault(_normalise_name(match.group(1)), {}).setdefault(specifier, [])
                files.append(path.relative_to(REPO_ROOT).as_posix())
    return pins


def _tilde_pin_mismatches(root: dict[str, dict[str, list[str]]], backend: dict[str, dict[str, list[str]]]) -> list[str]:
    """One line per package ``~=``-pinned on both sides that is not one single pin.

    Each side must resolve to exactly one specifier, and the two must agree.
    Comparing the sets of specifiers would pass a package pinned to two
    versions on each side (#11402), so a side that disagrees with itself is
    reported too, even when the other side carries the same two pins.
    """

    def describe(specs: dict[str, list[str]]) -> str:
        return ", ".join(f"{spec} ({', '.join(files)})" for spec, files in sorted(specs.items()))

    mismatches = []
    for name in sorted(root.keys() & backend.keys()):
        split = [side for side, specs in (("root", root[name]), ("backend", backend[name])) if len(specs) > 1]
        if not split and root[name].keys() == backend[name].keys():
            continue
        note = f" [{' and '.join(split)} pinned to more than one version]" if split else ""
        mismatches.append(f"{name}: root={describe(root[name])} backend={describe(backend[name])}{note}")
    return mismatches


def _pinned_version(path: Path, package: str) -> str:
    """The version in ``package``'s specifier (``~=``, ``>=`` or ``==``) in ``path``."""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        match = re.fullmatch(rf"{re.escape(package)}\s*(?:~=|>=|==)\s*([0-9][0-9A-Za-z.]*)", line, re.I)
        if match:
            return match.group(1)
    raise AssertionError(f"{package} has no ~=, >= or == specifier in {path}")


class RequirementsConsistencyTests(unittest.TestCase):
    def test_backend_requirements_are_mirrored_in_root_requirements(self) -> None:
        root_packages = _parse_package_names(ROOT_REQUIREMENTS)
        backend_packages = _parse_package_names(BACKEND_REQUIREMENTS)

        missing = backend_packages - root_packages - BACKEND_ONLY_ALLOWLIST

        self.assertFalse(
            missing,
            f"Package(s) {sorted(missing)} are pinned in backend/requirements.txt "
            "but missing from the root requirements.txt. scripts/run-backend.ps1 "
            "installs only from the root file, so a fresh local venv would be "
            "missing these and the backend would crash at import time "
            "(see issue #6016). Add them to requirements.txt, or add them to "
            "BACKEND_ONLY_ALLOWLIST in this test if they are genuinely "
            "backend-deploy-only tooling that backend/**/*.py never imports.",
        )

    def test_root_requirements_are_mirrored_in_backend_requirements(self) -> None:
        root_packages = _parse_package_names(ROOT_REQUIREMENTS)
        backend_packages = _parse_package_names(BACKEND_REQUIREMENTS)

        missing = root_packages - backend_packages - ROOT_ONLY_ALLOWLIST

        self.assertFalse(
            missing,
            f"Package(s) {sorted(missing)} are pinned in requirements.txt but "
            "missing from backend/requirements.txt. Lambda/Docker deployments "
            "install only the backend file and must not silently omit packages "
            "available to the local backend (see issue #6020). Add them to "
            "backend/requirements.txt, or add them to ROOT_ONLY_ALLOWLIST in "
            "this test if they are genuinely local-only tooling.",
        )

    def test_tilde_pins_match_across_root_and_backend(self) -> None:
        # Root and backend install the same libraries locally, in CI and on
        # Lambda, so a package pinned with ~= on both sides must carry the same
        # pin on both (#11377 fixed ~30 that had drifted; #11386 keeps them in
        # step). >=/== pins and one-sided ~= pins are deliberately not checked.
        mismatches = _tilde_pin_mismatches(_tilde_pins(ROOT_PIN_FILES), _tilde_pins(BACKEND_PIN_FILES))

        self.assertFalse(
            mismatches,
            "These ~= pins differ between the root requirements (requirements.txt, "
            "requirements-dev.txt) and the backend ones (backend/requirements.txt, "
            "backend/requirements-test.txt); bump both sides to the same version:\n" + "\n".join(mismatches),
        )

    def test_tilde_pin_check_reports_every_mismatch_and_ignores_other_pins(self) -> None:
        root = {
            "starlette": {"~=0.41.3": ["requirements.txt"]},
            "pytest": {"~=9.2.0": ["requirements-dev.txt"]},
            "only-root": {"~=1.0": ["requirements.txt"]},
            "attrs": {"~=24.3.0": ["requirements.txt"]},
        }
        backend = {
            "starlette": {"~=0.47.2": ["backend/requirements.txt"]},
            "pytest": {"~=9.2.0": ["backend/requirements-test.txt"]},
            "only-backend": {"~=2.0": ["backend/requirements.txt"]},
            "attrs": {"~=26.1.0": ["backend/requirements.txt"]},
        }

        self.assertEqual(
            _tilde_pin_mismatches(root, backend),
            [
                "attrs: root=~=24.3.0 (requirements.txt) backend=~=26.1.0 (backend/requirements.txt)",
                "starlette: root=~=0.41.3 (requirements.txt) backend=~=0.47.2 (backend/requirements.txt)",
            ],
        )

    def test_tilde_pin_check_reports_a_side_pinned_to_two_versions(self) -> None:
        # Both sides carry the same two pins, so the sets match; each side
        # still disagrees with itself (#11402).
        root = {"starlette": {"~=0.41.3": ["requirements.txt"], "~=0.47.2": ["requirements-dev.txt"]}}
        backend = {
            "starlette": {"~=0.41.3": ["backend/requirements.txt"], "~=0.47.2": ["backend/requirements-test.txt"]}
        }

        self.assertEqual(
            _tilde_pin_mismatches(root, backend),
            [
                "starlette: root=~=0.41.3 (requirements.txt), ~=0.47.2 (requirements-dev.txt) "
                "backend=~=0.41.3 (backend/requirements.txt), ~=0.47.2 (backend/requirements-test.txt) "
                "[root and backend pinned to more than one version]"
            ],
        )

    def test_tilde_pin_check_accepts_the_same_pin_repeated_on_one_side(self) -> None:
        root = {"pytest": {"~=9.2.0": ["requirements.txt", "requirements-dev.txt"]}}
        backend = {"pytest": {"~=9.2.0": ["backend/requirements-test.txt"]}}

        self.assertEqual(_tilde_pin_mismatches(root, backend), [])

    def test_tilde_pins_parse_extras_markers_and_normalise_names(self) -> None:
        pins = _tilde_pins((ROOT_REQUIREMENTS,))

        # A >=-pinned package is not a ~= pin; a marker is not part of the specifier.
        self.assertNotIn("protobuf", pins)
        self.assertEqual(list(pins["win-inet-pton"]), ["~=1.1.0"])

    def test_boto3_and_botocore_share_a_patch_version(self) -> None:
        # Released in lockstep (#11120). Backend boto3 stays a >= floor (#2810),
        # so the floor itself must match the botocore pin.
        for path in (ROOT_REQUIREMENTS, BACKEND_REQUIREMENTS):
            with self.subTest(path=path.name if path == ROOT_REQUIREMENTS else "backend/requirements.txt"):
                self.assertEqual(
                    _pinned_version(path, "boto3"),
                    _pinned_version(path, "botocore"),
                    f"boto3 and botocore must be bumped together to the same patch version in {path}.",
                )


if __name__ == "__main__":
    unittest.main()
