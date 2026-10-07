"""Tests for scripts/update_dependency_pins.py's cicaid pin updater (#6597).

Ported from leonarduk/issue-worm. All HTTP is mocked -- no network. File-
rewriting tests run against tmp_path; the one test that touches the repo's
real pins only reads them, to catch the pins and the regexes drifting apart.
"""

import ast
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from update_dependency_pins import (  # noqa: E402
    CICAID_PINS,
    REQUIREMENTS,
    PinError,
    _versions_equal,
    apply_update,
    current_pin,
    latest_version,
    main,
)

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "update-dependencies.yml"


def _workflow_check_regex() -> re.Pattern:
    """The CHECK_RE the update workflow validates the --check line with.

    Read out of the workflow rather than copied, so a change to either side
    fails a test instead of a nightly run.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^\s*CHECK_RE='([^']+)'", text, re.MULTILINE)
    assert match, f"no CHECK_RE assignment found in {WORKFLOW}"
    return re.compile(match.group(1))


CHECK_LINE_RE = _workflow_check_regex()

REQUIREMENTS_TEXT = (
    "# comment line stays untouched\n"
    "cicaid-devtools[dotenv] @ git+https://github.com/leonarduk/cicaid.git@v0.5.10\n"
    "cicaid-devtools-pro @ git+https://github.com/leonarduk/cicaid-pro.git@v0.19.0\n"
)
# The commented-out pin covers what the "^" anchor buys: only a real
# assignment at the start of a line counts.
CICAID_PINS_TEXT = (
    "# Only KEY=<tag> lines are honoured.\n"
    "# was CICAID_REF=v9.9.9 before the split\n"
    "CICAID_REF=v0.5.10\n"
    "CICAID_PRO_REF=v0.19.0\n"
)

PIN_FILES = {REQUIREMENTS: REQUIREMENTS_TEXT, CICAID_PINS: CICAID_PINS_TEXT}


def _read(root: Path, name: str) -> str:
    # Mirrors the helper's newline="" I/O so comparisons are byte-faithful.
    with open(root.joinpath(*name.split("/")), "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_repo(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root.joinpath(*name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root


def _assert_unchanged(root: Path) -> None:
    for name, original in PIN_FILES.items():
        assert _read(root, name) == original


@pytest.fixture
def repo(tmp_path):
    return _write_repo(tmp_path, PIN_FILES)


def test_free_update_rewrites_both_files_and_not_the_pro_pin(repo):
    assert apply_update("cicaid-devtools", "0.6.0", root=repo) == [REQUIREMENTS, CICAID_PINS]
    req = _read(repo, REQUIREMENTS)
    pins = _read(repo, CICAID_PINS)
    assert "cicaid.git@v0.6.0" in req
    assert "cicaid-pro.git@v0.19.0" in req
    assert "CICAID_REF=v0.6.0" in pins
    assert "CICAID_PRO_REF=v0.19.0" in pins


def test_pro_update_rewrites_both_files_and_not_the_free_pin(repo):
    assert apply_update("cicaid-devtools-pro", "0.20.0", root=repo) == [
        REQUIREMENTS,
        CICAID_PINS,
    ]
    req = _read(repo, REQUIREMENTS)
    pins = _read(repo, CICAID_PINS)
    assert "cicaid-pro.git@v0.20.0" in req
    assert "cicaid.git@v0.5.10" in req
    assert "CICAID_PRO_REF=v0.20.0" in pins
    assert "CICAID_REF=v0.5.10" in pins


def test_pins_file_comments_are_not_treated_as_pins(repo):
    assert current_pin("cicaid-devtools", root=repo) == "0.5.10"
    apply_update("cicaid-devtools", "0.6.0", root=repo)
    assert "# was CICAID_REF=v9.9.9 before the split" in _read(repo, CICAID_PINS)


def test_pins_file_main_ref_is_rewritten(repo):
    _write_repo(repo, {CICAID_PINS: CICAID_PINS_TEXT.replace("CICAID_REF=v0.5.10", "CICAID_REF=main")})
    # requirements still pins 0.5.10, so main is found but drifts.
    with pytest.raises(PinError, match="drifted"):
        current_pin("cicaid-devtools", root=repo)
    apply_update("cicaid-devtools", "0.6.0", root=repo)
    pins = _read(repo, CICAID_PINS)
    assert "CICAID_REF=v0.6.0" in pins
    assert "CICAID_REF=main" not in pins


@pytest.mark.parametrize("bad_ref", ["mainline", "maintenance"])
def test_refs_merely_starting_with_main_are_not_pins(repo, bad_ref):
    """Matching the "main" prefix would rewrite to a corrupted "v0.6.0line"."""
    _write_repo(
        repo,
        {CICAID_PINS: CICAID_PINS_TEXT.replace("CICAID_REF=v0.5.10", f"CICAID_REF={bad_ref}")},
    )
    with pytest.raises(PinError, match="no cicaid-devtools pin found"):
        current_pin("cicaid-devtools", root=repo)
    with pytest.raises(PinError, match="could not find the cicaid-devtools pin"):
        apply_update("cicaid-devtools", "0.6.0", root=repo)
    assert f"CICAID_REF={bad_ref}" in _read(repo, CICAID_PINS)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_main_ref_is_rewritten_with_either_line_ending(tmp_path, newline):
    files = {name: text.replace("\n", newline) for name, text in PIN_FILES.items()}
    files[CICAID_PINS] = files[CICAID_PINS].replace("CICAID_REF=v0.5.10", "CICAID_REF=main")
    _write_repo(tmp_path, files)
    apply_update("cicaid-devtools", "0.6.0", root=tmp_path)
    assert f"CICAID_REF=v0.6.0{newline}" in _read(tmp_path, CICAID_PINS)


def test_update_preserves_crlf(tmp_path):
    _write_repo(tmp_path, {n: t.replace("\n", "\r\n") for n, t in PIN_FILES.items()})
    apply_update("cicaid-devtools", "0.6.0", root=tmp_path)
    assert b"cicaid.git@v0.6.0\r\n" in (tmp_path / REQUIREMENTS).read_bytes()


def test_up_to_date_is_noop(repo):
    assert apply_update("cicaid-devtools", "0.5.10", root=repo) == []
    assert apply_update("cicaid-devtools-pro", "0.19.0", root=repo) == []
    _assert_unchanged(repo)


def test_dry_run_writes_nothing(repo):
    assert apply_update("cicaid-devtools", "0.6.0", root=repo, dry_run=True) == [
        REQUIREMENTS,
        CICAID_PINS,
    ]
    _assert_unchanged(repo)


def test_current_pin_reads_the_shared_version(repo):
    assert current_pin("cicaid-devtools", root=repo) == "0.5.10"
    assert current_pin("cicaid-devtools-pro", root=repo) == "0.19.0"


def test_drift_between_files_raises_naming_both(tmp_path, capsys):
    _write_repo(
        tmp_path,
        {
            REQUIREMENTS: REQUIREMENTS_TEXT.replace("cicaid.git@v0.5.10", "cicaid.git@v0.5.9"),
            CICAID_PINS: CICAID_PINS_TEXT,
        },
    )
    with (
        patch("update_dependency_pins._http_json", return_value={"tag_name": "v0.6.0"}),
        patch("update_dependency_pins.ROOT", tmp_path),
    ):
        assert main(["cicaid-devtools", "--check"]) == 1
    err = capsys.readouterr().err
    assert f"{REQUIREMENTS} has v0.5.9" in err
    assert f"{CICAID_PINS} has v0.5.10" in err


def test_missing_pin_raises(tmp_path):
    _write_repo(tmp_path, {REQUIREMENTS: "# nothing pinned\n", CICAID_PINS: CICAID_PINS_TEXT})
    with pytest.raises(PinError, match="no cicaid-devtools-pro pin found"):
        current_pin("cicaid-devtools-pro", root=tmp_path)


def test_latest_free_strips_v_and_does_not_pass_token():
    with patch("update_dependency_pins._http_json", return_value={"tag_name": "v0.6.0"}) as mock_http:
        assert latest_version("cicaid-devtools", token="secret") == "0.6.0"
    mock_http.assert_called_once_with("https://api.github.com/repos/leonarduk/cicaid/releases/latest", token=None)


def test_latest_pro_passes_token():
    with patch("update_dependency_pins._http_json", return_value={"tag_name": "v0.20.0"}) as mock_http:
        assert latest_version("cicaid-devtools-pro", token="secret") == "0.20.0"
    mock_http.assert_called_once_with(
        "https://api.github.com/repos/leonarduk/cicaid-pro/releases/latest", token="secret"
    )


def test_latest_pro_without_token_raises_clear_error():
    with patch("update_dependency_pins._http_json") as mock_http:
        with pytest.raises(PinError, match="GITHUB_TOKEN"):
            latest_version("cicaid-devtools-pro")
    mock_http.assert_not_called()


def test_latest_pro_fetch_error_names_the_likely_cause():
    with patch(
        "update_dependency_pins._http_json",
        side_effect=PinError("failed to fetch https://example.invalid: HTTP Error 404"),
    ):
        with pytest.raises(PinError, match="token has expired or lost read access"):
            latest_version("cicaid-devtools-pro", token="secret")


def test_latest_rejects_non_v_tag():
    with patch("update_dependency_pins._http_json", return_value={"tag_name": "0.6.0"}):
        with pytest.raises(PinError, match="v-prefixed"):
            latest_version("cicaid-devtools")


def test_unknown_dependency_rejected():
    with pytest.raises(PinError, match="unknown dependency"):
        latest_version("ollama-tools")


def test_check_mode_reports_update_without_writing(repo, capsys):
    with (
        patch("update_dependency_pins._http_json", return_value={"tag_name": "v0.6.0"}),
        patch("update_dependency_pins.ROOT", repo),
    ):
        assert main(["cicaid-devtools", "--check", "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()
    # The workflow parses this exact line; --check wins over --dry-run.
    assert out == ["UPDATE cicaid-devtools 0.5.10 -> 0.6.0"]
    assert CHECK_LINE_RE.match(out[0])
    _assert_unchanged(repo)


def test_check_mode_treats_zero_padding_as_up_to_date(repo, capsys):
    with (
        patch("update_dependency_pins._http_json", return_value={"tag_name": "v0.5.10.0"}),
        patch("update_dependency_pins.ROOT", repo),
    ):
        assert main(["cicaid-devtools", "--check"]) == 0
    assert capsys.readouterr().out.splitlines() == ["UP-TO-DATE cicaid-devtools 0.5.10"]


def test_write_mode_updates_and_exits_zero(repo, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    with (
        patch("update_dependency_pins._http_json", return_value={"tag_name": "v0.20.0"}),
        patch("update_dependency_pins.ROOT", repo),
    ):
        assert main(["cicaid-devtools-pro"]) == 0
    assert "CICAID_PRO_REF=v0.20.0" in _read(repo, CICAID_PINS)


def test_check_line_regex_accepts_local_versions_and_rejects_shell_syntax():
    assert CHECK_LINE_RE.match("UPDATE cicaid-devtools 0.5.10 -> 0.99.0+abc123")
    assert not CHECK_LINE_RE.match("UPDATE cicaid-devtools 0.5.10 -> 1.0;rm -rf /")


@pytest.mark.parametrize(
    ("left", "right", "equal"),
    [
        ("1.0", "1.0.0", True),
        ("0.9.0.0", "0.9", True),
        ("1.0.0", "1.0.1", False),
        ("2.10", "2.1", False),
        ("0.9.0", "0.9.0rc1", False),
        ("1.0.0+abc123", "1.0.0", False),
        ("0.9.0RC1", "0.9.0rc1", True),
        ("nightly", "nightly", True),
        ("nightly", "weekly", False),
    ],
)
def test_versions_equal(left, right, equal):
    assert _versions_equal(left, right) is equal
    assert _versions_equal(right, left) is equal


def test_real_repo_pins_are_readable_and_agree():
    """A hand-edited pin in one file only fails here, not in a nightly run."""
    assert current_pin("cicaid-devtools", root=REPO_ROOT)
    assert current_pin("cicaid-devtools-pro", root=REPO_ROOT)


def test_review_workflow_reads_both_pins_file_keys():
    """_ai-pr-review.yml installs from the same keys this script rewrites."""
    text = (REPO_ROOT / ".github" / "workflows" / "_ai-pr-review.yml").read_text(encoding="utf-8")
    assert "read_ref CICAID_REF" in text
    assert "read_ref CICAID_PRO_REF" in text


def test_script_imports_only_stdlib():
    """It runs when pins are stale/broken, so it must not import cicaid."""
    source = (REPO_ROOT / "scripts" / "update_dependency_pins.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    stdlib = {
        "__future__",
        "argparse",
        "dataclasses",
        "json",
        "os",
        "re",
        "sys",
        "urllib",
        "pathlib",
    }
    assert imported <= stdlib, f"non-stdlib imports found: {imported - stdlib}"
