"""Unit tests for scripts/check_lockfile_platform_coverage.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_lockfile_platform_coverage.py"
spec = importlib.util.spec_from_file_location("check_lockfile_platform_coverage", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(_mod)  # type: ignore[union-attr]
platforms_in_lockfile = _mod.platforms_in_lockfile
main = _mod.main


def _write_lockfile(path: Path, packages: dict) -> None:
    path.write_text(json.dumps({"packages": packages}), encoding="utf-8")


# ---------------------------------------------------------------------------
# platforms_in_lockfile
# ---------------------------------------------------------------------------


class TestPlatformsInLockfile:
    def test_collects_os_values_from_optional_packages(self, tmp_path: Path) -> None:
        f = tmp_path / "package-lock.json"
        _write_lockfile(
            f,
            {
                "node_modules/@esbuild/linux-x64": {
                    "optional": True,
                    "os": ["linux"],
                },
                "node_modules/@esbuild/win32-x64": {
                    "optional": True,
                    "os": ["win32"],
                },
            },
        )
        assert platforms_in_lockfile(f) == {"linux", "win32"}

    def test_ignores_non_optional_packages(self, tmp_path: Path) -> None:
        f = tmp_path / "package-lock.json"
        _write_lockfile(
            f,
            {
                "node_modules/react": {"version": "19.0.0"},
                "node_modules/@esbuild/linux-x64": {
                    "optional": True,
                    "os": ["linux"],
                },
            },
        )
        assert platforms_in_lockfile(f) == {"linux"}

    def test_no_platform_restricted_packages_returns_empty_set(self, tmp_path: Path) -> None:
        f = tmp_path / "package-lock.json"
        _write_lockfile(f, {"node_modules/react": {"version": "19.0.0"}})
        assert platforms_in_lockfile(f) == set()


# ---------------------------------------------------------------------------
# main() end-to-end
# ---------------------------------------------------------------------------


class TestMain:
    def _patch_lockfiles(self, monkeypatch: pytest.MonkeyPatch, *lockfiles: Path) -> None:
        monkeypatch.setattr(_mod, "LOCKFILES", tuple(lockfiles))

    def test_full_platform_coverage_returns_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "package-lock.json"
        _write_lockfile(
            f,
            {
                "node_modules/@esbuild/linux-x64": {"optional": True, "os": ["linux"]},
                "node_modules/@esbuild/win32-x64": {"optional": True, "os": ["win32"]},
                "node_modules/@esbuild/darwin-x64": {"optional": True, "os": ["darwin"]},
            },
        )
        self._patch_lockfiles(monkeypatch, f)
        assert main() == 0
        assert "OK" in capsys.readouterr().out

    def test_missing_linux_platform_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "package-lock.json"
        _write_lockfile(
            f,
            {
                "node_modules/@esbuild/win32-x64": {"optional": True, "os": ["win32"]},
                "node_modules/@esbuild/darwin-x64": {"optional": True, "os": ["darwin"]},
            },
        )
        self._patch_lockfiles(monkeypatch, f)
        assert main() == 1
        err = capsys.readouterr().err
        assert "ERROR" in err
        assert "linux" in err

    def test_no_platform_restricted_packages_is_not_a_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "package-lock.json"
        _write_lockfile(f, {"node_modules/react": {"version": "19.0.0"}})
        self._patch_lockfiles(monkeypatch, f)
        assert main() == 0

    def test_missing_lockfile_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._patch_lockfiles(monkeypatch, tmp_path / "nonexistent-lock.json")
        assert main() == 0

    def test_multiple_lockfiles_report_all_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        good = tmp_path / "good-lock.json"
        bad = tmp_path / "bad-lock.json"
        _write_lockfile(
            good,
            {
                "node_modules/@esbuild/linux-x64": {"optional": True, "os": ["linux"]},
                "node_modules/@esbuild/win32-x64": {"optional": True, "os": ["win32"]},
                "node_modules/@esbuild/darwin-x64": {"optional": True, "os": ["darwin"]},
            },
        )
        _write_lockfile(
            bad,
            {
                "node_modules/@esbuild/win32-x64": {"optional": True, "os": ["win32"]},
            },
        )
        self._patch_lockfiles(monkeypatch, good, bad)
        assert main() == 1
        err = capsys.readouterr().err
        assert str(bad.name) in err
