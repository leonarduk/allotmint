"""Unit tests for scripts/check_contract_version_sync.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the script as a module without executing the __main__ block.
# spec.loader.exec_module runs at import time; if the script is missing the
# entire test module will fail to collect with an informative ImportError.
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_contract_version_sync.py"
spec = importlib.util.spec_from_file_location("check_contract_version_sync", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(_mod)  # type: ignore[union-attr]
extract_contract_version = _mod.extract_contract_version
main = _mod.main


# ---------------------------------------------------------------------------
# extract_contract_version
# ---------------------------------------------------------------------------

class TestExtractContractVersion:
    def test_python_style_single_quotes(self, tmp_path: Path) -> None:
        f = tmp_path / "contracts.py"
        f.write_text("SPA_RESPONSE_CONTRACT_VERSION = '2.1.0'\n")
        assert extract_contract_version(f) == "2.1.0"

    def test_typescript_style_double_quotes(self, tmp_path: Path) -> None:
        f = tmp_path / "spa.ts"
        f.write_text('export const SPA_RESPONSE_CONTRACT_VERSION = "3.0";\n')
        assert extract_contract_version(f) == "3.0"

    def test_mismatched_quotes_not_matched(self, tmp_path: Path) -> None:
        """Opening double-quote closed by single-quote must NOT match."""
        f = tmp_path / "bad.py"
        f.write_text("SPA_RESPONSE_CONTRACT_VERSION = \"1.0'\n")
        with pytest.raises(ValueError, match="Could not find"):
            extract_contract_version(f)

    def test_missing_definition_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("# nothing here\n")
        with pytest.raises(ValueError, match="Could not find"):
            extract_contract_version(f)

    def test_duplicate_definition_raises(self, tmp_path: Path) -> None:
        """Two real (non-comment) definitions on separate lines must raise."""
        f = tmp_path / "dup.py"
        f.write_text(
            "SPA_RESPONSE_CONTRACT_VERSION = '0.9'\n"
            "SPA_RESPONSE_CONTRACT_VERSION = '1.0'\n"
        )
        with pytest.raises(ValueError, match="2 occurrences"):
            extract_contract_version(f)

    def test_full_line_comment_is_ignored(self, tmp_path: Path) -> None:
        """A full-line Python comment referencing the old version is ignored."""
        f = tmp_path / "contracts.py"
        f.write_text(
            "# SPA_RESPONSE_CONTRACT_VERSION = '0.9'  # previous version\n"
            "SPA_RESPONSE_CONTRACT_VERSION = '1.0'\n"
        )
        assert extract_contract_version(f) == "1.0"

    def test_typescript_full_line_comment_is_ignored(self, tmp_path: Path) -> None:
        """A full-line TypeScript // comment referencing the old version is ignored."""
        f = tmp_path / "spa.ts"
        f.write_text(
            '// SPA_RESPONSE_CONTRACT_VERSION = "0.9";  // old\n'
            'export const SPA_RESPONSE_CONTRACT_VERSION = "1.0";\n'
        )
        assert extract_contract_version(f) == "1.0"

    def test_inline_comment_with_old_version_is_stripped(self, tmp_path: Path) -> None:
        """An inline trailing comment that mentions the old version must not
        trigger the duplicate guard.
        """
        f = tmp_path / "contracts.py"
        f.write_text(
            "SPA_RESPONSE_CONTRACT_VERSION = '1.0'  "
            "# bumped from SPA_RESPONSE_CONTRACT_VERSION = '0.9'\n"
        )
        assert extract_contract_version(f) == "1.0"

    def test_typescript_inline_comment_with_old_version_is_stripped(self, tmp_path: Path) -> None:
        """Same check for TypeScript inline // comment."""
        f = tmp_path / "spa.ts"
        f.write_text(
            'export const SPA_RESPONSE_CONTRACT_VERSION = "1.0";  '
            '// was SPA_RESPONSE_CONTRACT_VERSION = "0.9"\n'
        )
        assert extract_contract_version(f) == "1.0"

    def test_file_not_found_propagates(self, tmp_path: Path) -> None:
        with pytest.raises(OSError):
            extract_contract_version(tmp_path / "nonexistent.py")


# ---------------------------------------------------------------------------
# main() end-to-end
# ---------------------------------------------------------------------------

class TestMain:
    def _patch_paths(self, monkeypatch: pytest.MonkeyPatch, py_file: Path, ts_file: Path) -> None:
        monkeypatch.setattr(_mod, "PYTHON_CONTRACT", py_file)
        monkeypatch.setattr(_mod, "TYPESCRIPT_CONTRACT", ts_file)

    def test_versions_match_returns_0(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        py = tmp_path / "contracts.py"
        ts = tmp_path / "spa.ts"
        py.write_text("SPA_RESPONSE_CONTRACT_VERSION = '1.0'\n")
        ts.write_text('SPA_RESPONSE_CONTRACT_VERSION = "1.0";\n')
        self._patch_paths(monkeypatch, py, ts)
        assert main() == 0
        assert "in sync" in capsys.readouterr().out

    def test_versions_mismatch_returns_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        py = tmp_path / "contracts.py"
        ts = tmp_path / "spa.ts"
        py.write_text("SPA_RESPONSE_CONTRACT_VERSION = '1.0'\n")
        ts.write_text('SPA_RESPONSE_CONTRACT_VERSION = "2.0";\n')
        self._patch_paths(monkeypatch, py, ts)
        assert main() == 1
        assert "mismatch" in capsys.readouterr().err

    def test_missing_file_returns_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        py = tmp_path / "contracts.py"
        py.write_text("SPA_RESPONSE_CONTRACT_VERSION = '1.0'\n")
        self._patch_paths(monkeypatch, py, tmp_path / "nonexistent.ts")
        assert main() == 1
        assert "ERROR" in capsys.readouterr().err

    def test_version_not_found_returns_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        py = tmp_path / "contracts.py"
        ts = tmp_path / "spa.ts"
        py.write_text("SPA_RESPONSE_CONTRACT_VERSION = '1.0'\n")
        ts.write_text("// no version here\n")
        self._patch_paths(monkeypatch, py, ts)
        assert main() == 1
        assert "ERROR" in capsys.readouterr().err
