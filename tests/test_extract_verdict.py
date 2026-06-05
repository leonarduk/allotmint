from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_extract_verdict():
    spec = importlib.util.spec_from_file_location(
        "extract_verdict_test", SCRIPTS_DIR / "extract_verdict.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return load_extract_verdict()


# --- extract_verdict() unit tests ---


def test_extract_verdict_approve(mod):
    assert mod.extract_verdict("blah\n**APPROVE**") == "APPROVE"


def test_extract_verdict_request_changes(mod):
    assert mod.extract_verdict("nope\n**REQUEST CHANGES**") == "REQUEST CHANGES"


def test_extract_verdict_none(mod):
    assert mod.extract_verdict("no verdict here") is None


# --- main() integration tests, parametrized over both providers ---


@pytest.mark.parametrize("provider", ["Claude", "GPT"])
def test_main_approve(tmp_path, capsys, mod, provider):
    f = tmp_path / "review.md"
    f.write_text("Looks good\n**APPROVE**")
    assert mod.main(str(f), provider) == 0
    assert f"✓ {provider} review: APPROVED" in capsys.readouterr().out


@pytest.mark.parametrize("provider", ["Claude", "GPT"])
def test_main_request_changes(tmp_path, capsys, mod, provider):
    f = tmp_path / "review.md"
    f.write_text("Fix this\n**REQUEST CHANGES**")
    assert mod.main(str(f), provider) == 1
    assert f"✗ {provider} review: CHANGES REQUESTED" in capsys.readouterr().out


@pytest.mark.parametrize("provider", ["Claude", "GPT"])
def test_main_no_verdict(tmp_path, capsys, mod, provider):
    f = tmp_path / "review.md"
    f.write_text("Some review without a verdict line.")
    assert mod.main(str(f), provider) == 1
    assert "did not include a valid verdict" in capsys.readouterr().err


@pytest.mark.parametrize("provider", ["Claude", "GPT"])
def test_main_empty_file(tmp_path, capsys, mod, provider):
    f = tmp_path / "review.md"
    f.write_text("")
    assert mod.main(str(f), provider) == 1
    assert f"ERROR: {provider} review output was empty" in capsys.readouterr().err


@pytest.mark.parametrize("provider", ["Claude", "GPT"])
def test_main_missing_file(capsys, mod, provider):
    assert mod.main("/nonexistent/path/review.md", provider) == 1
    assert "Review file not found" in capsys.readouterr().err
