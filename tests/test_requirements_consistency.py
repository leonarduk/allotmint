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

ROOT_REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"
BACKEND_REQUIREMENTS = Path(__file__).resolve().parents[1] / "backend" / "requirements.txt"

# Packages that are legitimately backend-only build/deploy tooling and are not
# imported by backend/**/*.py at runtime, so they don't need to be mirrored
# into the root requirements.txt used by the local dev server.
BACKEND_ONLY_ALLOWLIST = {"setuptools"}

# Keep exemptions explicit and narrowly limited to packages that are genuinely
# needed only by local tooling. Runtime dependencies belong in both files so
# local development and Lambda/Docker deployments install the same package set.
ROOT_ONLY_ALLOWLIST: set[str] = set()

_PACKAGE_NAME_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


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


if __name__ == "__main__":
    unittest.main()
