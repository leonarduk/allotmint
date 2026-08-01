import json
import os
import subprocess

import pytest

import scripts.developer_tools.o_review_issue as n


@pytest.fixture
def git_repo(tmp_path):
    """A minimal git repo with a couple of tracked files, for file-hint resolution tests."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    nested = tmp_path / "scripts" / "build_tools"
    nested.mkdir(parents=True)
    (nested / "extract_pr_comments.py").write_text(
        "def widget_test_stub_symbol(url):\n    return []\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_parse_review_response_extracts_title_and_body():
    response = "TITLE: Fixed title\nBODY:\n## What\nUpdated content\n"
    title, body = n.parse_review_response(response, "old title", "old body")
    assert title == "Fixed title"
    assert body == "## What\nUpdated content"


def test_parse_review_response_falls_back_on_malformed_response():
    response = "I refuse to answer in the requested format."
    title, body = n.parse_review_response(response, "old title", "old body")
    assert (title, body) == ("old title", "old body")


def test_parse_review_response_falls_back_on_empty_body():
    response = "TITLE: New title\nBODY:\n"
    title, body = n.parse_review_response(response, "old title", "old body")
    assert (title, body) == ("old title", "old body")


def test_looks_like_content_loss_true_when_much_shorter():
    original = "## What\n" + ("detail line\n" * 50)
    revised = "## What\nshort"
    assert n.looks_like_content_loss(original, revised)


def test_looks_like_content_loss_false_when_similar_length():
    original = "## What\nsome detail here"
    revised = "## What\nsome updated detail here"
    assert not n.looks_like_content_loss(original, revised)


def test_looks_like_content_loss_false_when_original_is_empty():
    assert not n.looks_like_content_loss("", "")


def test_run_review_local_returns_none_when_ollama_unreachable(monkeypatch):
    monkeypatch.setattr(n, "validate_model_source", lambda model_source: False)
    assert n.run_review(n.LOCAL, "title", "body") is None


def test_run_review_local_returns_response(monkeypatch):
    monkeypatch.setattr(n, "validate_model_source", lambda model_source: True)
    monkeypatch.setattr(n, "fetch_review", lambda model_source, prompt: "TITLE: t\nBODY:\nb")
    assert n.run_review(n.LOCAL, "title", "body") == "TITLE: t\nBODY:\nb"


def test_load_env_file_sets_missing_vars(monkeypatch, tmp_path):
    # python-dotenv is a dev-only dependency (requirements-dev.txt); some CI jobs
    # install only backend/requirements.txt, where load_env_file is a documented no-op.
    pytest.importorskip("dotenv")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=from-env-file\n", encoding="utf-8")
    n.load_env_file(env_file)
    # Register with monkeypatch so it's still tracked for auto-cleanup after the test.
    monkeypatch.setenv("DEEPSEEK_API_KEY", os.environ["DEEPSEEK_API_KEY"])
    assert os.environ["DEEPSEEK_API_KEY"] == "from-env-file"


def test_load_env_file_missing_file_is_a_noop(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    n.load_env_file(tmp_path / "does_not_exist.env")
    assert "DEEPSEEK_API_KEY" not in os.environ


def test_run_review_cloud_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert n.run_review(n.CLOUD, "title", "body") is None


def test_run_review_cloud_returns_response(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    monkeypatch.setattr(n, "fetch_review", lambda model_source, prompt: "TITLE: t\nBODY:\nb")
    assert n.run_review(n.CLOUD, "title", "body") == "TITLE: t\nBODY:\nb"


def test_run_review_returns_none_on_empty_response(monkeypatch):
    monkeypatch.setattr(n, "validate_model_source", lambda model_source: True)
    monkeypatch.setattr(n, "fetch_review", lambda model_source, prompt: "   ")
    assert n.run_review(n.LOCAL, "title", "body") is None


def test_fetch_issue_parses_gh_json(monkeypatch):
    payload = json.dumps({"number": 42, "title": "T", "body": "B", "state": "OPEN", "url": "u"})
    monkeypatch.setattr(
        n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=0, stdout=payload)
    )
    issue = n.fetch_issue("owner", "repo", 42)
    assert issue == {"number": 42, "title": "T", "body": "B", "state": "OPEN", "url": "u"}


def test_fetch_issue_exits_on_gh_failure(monkeypatch):
    monkeypatch.setattr(
        n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=1, stderr="not found")
    )
    try:
        n.fetch_issue("owner", "repo", 42)
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert exc.code == 1


def test_update_issue_dry_run_skips_gh_call(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("gh should not be called in dry-run mode")

    monkeypatch.setattr(n.subprocess, "run", fail_if_called)
    assert n.update_issue("owner", "repo", 1, "title", "body", dry_run=True) is True


def test_update_issue_reports_failure(monkeypatch):
    monkeypatch.setattr(
        n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=1, stderr="boom")
    )
    assert n.update_issue("owner", "repo", 1, "title", "body", dry_run=False) is False


def test_update_issue_success(monkeypatch):
    monkeypatch.setattr(n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=0))
    assert n.update_issue("owner", "repo", 1, "title", "body", dry_run=False) is True


def test_load_template_sections_reads_real_bug_report_template():
    sections = n.load_template_sections()
    assert sections == [
        "What",
        "Why",
        "How",
        "Files Affected",
        "Constraints",
        "LLM tier",
        "Success looks like",
        "Failure looks like",
    ]


def test_load_template_sections_falls_back_when_file_missing(tmp_path):
    missing = tmp_path / "does_not_exist.md"
    assert n.load_template_sections(missing) == n.FALLBACK_TEMPLATE_SECTIONS


def test_missing_sections_detects_gaps():
    body = "## What\nsome text\n\n## Why\nreason\n"
    assert n.missing_sections(body, ["What", "Why", "How"]) == ["How"]


def test_missing_sections_empty_when_all_present():
    body = "## What\ntext\n\n## Why\ntext\n"
    assert n.missing_sections(body, ["What", "Why"]) == []


def test_missing_sections_recognizes_deeper_heading_levels():
    # An issue using '###' throughout (#5820) must not have every one of those
    # sections misreported as missing just because they aren't '##'.
    body = "## What\ntext\n\n### Why\nreason\n\n#### How\nsteps\n"
    assert n.missing_sections(body, ["What", "Why", "How", "Constraints"]) == ["Constraints"]


def test_build_review_prompt_has_no_feedback_section_by_default():
    prompt = n.build_review_prompt("title", "## What\nbody")
    assert "The user reviewed a previous revision" not in prompt
    assert "'## What'" in prompt


def test_build_review_prompt_includes_feedback_when_given():
    prompt = n.build_review_prompt("title", "## What\nbody", feedback="please add repro steps")
    assert "The user reviewed a previous revision" in prompt
    assert "please add repro steps" in prompt


def test_prompt_for_disposition_apply_on_blank_or_y(monkeypatch):
    for answer in ("", "y", "Yes"):
        monkeypatch.setattr("builtins.input", lambda _prompt, a=answer: a)
        assert n.prompt_for_disposition() == ("apply", None)


def test_prompt_for_disposition_abort_on_n(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert n.prompt_for_disposition() == ("abort", None)


def test_prompt_for_disposition_treats_other_text_as_feedback(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "please tighten the Why section")
    action, feedback = n.prompt_for_disposition()
    assert action == "retry"
    assert feedback == "please tighten the Why section"


def test_prompt_for_disposition_aborts_on_eof(monkeypatch):
    def _raise_eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise_eof)
    assert n.prompt_for_disposition() == ("abort", None)


def test_files_affected_is_unresolved_true_for_unknown():
    body = "## What\ntext\n\n## Files Affected\nUnknown\n\n## Constraints\nnone\n"
    assert n.files_affected_is_unresolved(body)


def test_files_affected_is_unresolved_true_for_empty_section():
    body = "## What\ntext\n\n## Files Affected\n\n## Constraints\nnone\n"
    assert n.files_affected_is_unresolved(body)


def test_files_affected_is_unresolved_false_when_paths_present():
    body = "## Files Affected\n- `real/path.py`\n"
    assert not n.files_affected_is_unresolved(body)


def test_files_affected_is_unresolved_true_when_section_missing():
    # A missing heading is itself an unresolved state (#5845), not a pass-through.
    assert n.files_affected_is_unresolved("## What\nno such section\n")


def test_files_affected_is_unresolved_recognizes_deeper_heading_level():
    body = "### Files Affected\n- `real/path.py`\n"
    assert not n.files_affected_is_unresolved(body)


def test_post_unresolved_files_comment_dry_run_skips_gh_call(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("gh should not be called in dry-run mode")

    monkeypatch.setattr(n.subprocess, "run", fail_if_called)
    assert n.post_unresolved_files_comment("owner", "repo", 1, dry_run=True) is True


def test_post_unresolved_files_comment_success(monkeypatch):
    monkeypatch.setattr(n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=0))
    assert n.post_unresolved_files_comment("owner", "repo", 1, dry_run=False) is True


def test_post_unresolved_files_comment_reports_failure(monkeypatch):
    monkeypatch.setattr(
        n.subprocess, "run", lambda *a, **k: _FakeResult(returncode=1, stderr="boom")
    )
    assert n.post_unresolved_files_comment("owner", "repo", 1, dry_run=False) is False


def test_list_repo_files_returns_tracked_paths(git_repo):
    files = n.list_repo_files(git_repo)
    assert "README.md" in files
    assert "scripts/build_tools/extract_pr_comments.py" in files


def test_list_repo_files_returns_empty_on_failure(tmp_path):
    # tmp_path is not a git repo, so `git ls-files` fails.
    assert n.list_repo_files(tmp_path) == []


def test_find_repo_file_hints_resolves_backticked_symbol_to_real_path(git_repo):
    hints = n.find_repo_file_hints("Fix `widget_test_stub_symbol` retry handling.", git_repo)
    assert hints == {"widget_test_stub_symbol": ["scripts/build_tools/extract_pr_comments.py"]}


def test_find_repo_file_hints_resolves_bare_filename(git_repo):
    hints = n.find_repo_file_hints("See README.md for context.", git_repo)
    assert hints == {"README.md": ["README.md"]}


def test_find_repo_file_hints_resolves_powershell_and_bash_scripts(git_repo):
    (git_repo / "deploy.ps1").write_text("Write-Host 'hi'\n", encoding="utf-8")
    (git_repo / "deploy.sh").write_text("echo hi\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add scripts"], cwd=git_repo, check=True)
    hints = n.find_repo_file_hints(
        "The script `deploy.ps1` and `deploy.sh` both need work.", git_repo
    )
    assert hints == {"deploy.ps1": ["deploy.ps1"], "deploy.sh": ["deploy.sh"]}


def test_find_repo_file_hints_ignores_unknown_names(git_repo):
    text = "Update `totally_missing_symbol` in nonexistent.py."
    assert n.find_repo_file_hints(text, git_repo) == {}


def test_find_repo_file_hints_ignores_short_symbols(git_repo):
    (git_repo / "id.py").write_text("def id():\n    pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add id.py"], cwd=git_repo, check=True)
    assert n.find_repo_file_hints("Fix `id` please.", git_repo) == {}


def test_find_repo_file_hints_skips_ambiguous_filename(git_repo):
    # Two files share the basename 'config.py' -- neither is confidently "the" match.
    other_dir = git_repo / "other"
    other_dir.mkdir()
    (other_dir / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "add duplicate basename"], cwd=git_repo, check=True
    )
    (git_repo / "config.py").write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add root config.py"], cwd=git_repo, check=True)
    assert n.find_repo_file_hints("See config.py for details.", git_repo) == {}


def test_find_repo_file_hints_skips_ambiguous_symbol(git_repo):
    # The same symbol name is defined in two different files -- ambiguous, so unresolved.
    other_dir = git_repo / "other"
    other_dir.mkdir()
    (other_dir / "helpers.py").write_text(
        "def widget_test_stub_symbol():\n    pass\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add duplicate symbol"], cwd=git_repo, check=True)
    hints = n.find_repo_file_hints("Fix `widget_test_stub_symbol` retry handling.", git_repo)
    assert hints == {}


def test_find_repo_file_hints_ignores_stale_files_affected_section(git_repo):
    # A prior pass's (possibly wrong) Files Affected entry shouldn't re-confirm itself just
    # because the filename it names happens to exist in the repo.
    text = "## What\nsome unrelated bug.\n\n## Files Affected\n- `README.md`\n"
    assert n.find_repo_file_hints(text, git_repo) == {}


def test_strip_files_affected_section_removes_only_that_section():
    text = "## What\nsome text\n\n## Files Affected\n- `a.py`\n- `b.py`\n\n## Constraints\nnone\n"
    result = n.strip_files_affected_section(text)
    assert "a.py" not in result
    assert "b.py" not in result
    assert "## What\nsome text" in result
    assert "## Constraints\nnone" in result


def test_strip_files_affected_section_noop_when_section_absent():
    text = "## What\nsome text\n\n## Constraints\nnone\n"
    assert n.strip_files_affected_section(text) == text


def test_strip_files_affected_section_recognizes_deeper_heading_level():
    text = "## What\nsome text\n\n### Files Affected\n- `a.py`\n\n### Constraints\nnone\n"
    result = n.strip_files_affected_section(text)
    assert "a.py" not in result
    assert "### Constraints\nnone" in result


def test_format_file_hints_empty():
    assert n.format_file_hints({}) == ""


def test_format_file_hints_renders_bullet_list():
    text = n.format_file_hints({"foo": ["a/foo.py"], "bar": ["b/bar.py"]})
    assert "Known repository file locations" in text
    assert "- `foo` -> `a/foo.py`" in text
    assert "- `bar` -> `b/bar.py`" in text


def test_build_review_prompt_includes_file_hints_section():
    prompt = n.build_review_prompt(
        "title", "## What\nbody", file_hints={"fetch_paginated": ["scripts/foo.py"]}
    )
    assert "Known repository file locations" in prompt
    assert "`fetch_paginated` -> `scripts/foo.py`" in prompt


def test_build_review_prompt_no_file_hints_section_by_default():
    prompt = n.build_review_prompt("title", "## What\nbody")
    assert "Known repository file locations for names mentioned" not in prompt


def test_apply_known_file_paths_replaces_model_guess():
    body = (
        "## What\nsome text\n\n## Files Affected\n- `fetch_paginated.py`\n\n## Constraints\nnone\n"
    )
    hints = {"fetch_paginated": ["scripts/build_tools/extract_pr_comments.py"]}
    result = n.apply_known_file_paths(body, hints)
    assert "- `scripts/build_tools/extract_pr_comments.py`" in result
    assert "fetch_paginated.py" not in result


def test_apply_known_file_paths_recognizes_deeper_heading_level():
    # #5820: a body using '###' throughout must still have its Files Affected
    # section found and replaced, not treated as missing and duplicated at '##'.
    body = "### What\nsome text\n\n### Files Affected\n- `old.py`\n\n### Constraints\nnone\n"
    hints = {"old": ["real/old.py"]}
    result = n.apply_known_file_paths(body, hints)
    assert result.count("Files Affected") == 1
    assert "### Files Affected\n- `real/old.py`" in result
    assert "## Constraints\nnone" in result


def test_apply_known_file_paths_dedupes_and_sorts_multiple_matches():
    body = "## Files Affected\nUnknown\n\n## Constraints\nnone\n"
    hints = {
        "foo": ["b/foo.py", "a/foo.py"],
        "bar": ["a/foo.py"],
    }
    result = n.apply_known_file_paths(body, hints)
    files_section = result.split("## Constraints")[0]
    assert files_section.count("a/foo.py") == 1
    assert files_section.index("a/foo.py") < files_section.index("b/foo.py")


def test_apply_known_file_paths_forces_unknown_without_hints():
    # A model-guessed path is never trusted, even if it looks plausible -- without a
    # confidently resolved hint, the section is forced to "Unknown" rather than left alone.
    body = "## Files Affected\n- `backend/app.py`\n\n## Constraints\nnone\n"
    result = n.apply_known_file_paths(body, {})
    assert "backend/app.py" not in result
    assert "## Files Affected\nUnknown" in result


def test_apply_known_file_paths_inserts_section_before_next_canonical_section():
    # The model dropped the 'Files Affected' heading entirely (#5650) -- it must still be
    # inserted, in its canonical template position, not silently skipped.
    body = "## What\ntext\n\n## Constraints\nsome constraint\n"
    hints = {"foo": ["a/foo.py"]}
    sections = ["What", "Files Affected", "Constraints"]
    result = n.apply_known_file_paths(body, hints, sections=sections)
    assert "## Files Affected\n- `a/foo.py`\n\n## Constraints\nsome constraint" in result
    assert result.index("## Files Affected") < result.index("## Constraints")


def test_apply_known_file_paths_appends_section_when_no_later_section_present():
    body = "## What\nno files affected section here\n"
    hints = {"foo": ["a/foo.py"]}
    sections = ["What", "Files Affected"]
    result = n.apply_known_file_paths(body, hints, sections=sections)
    assert result.rstrip("\n").endswith("## Files Affected\n- `a/foo.py`")
    assert "## What\nno files affected section here" in result


def test_apply_known_file_paths_inserts_unknown_when_section_missing_and_no_hints():
    body = "## What\ntext\n\n## Constraints\nnone\n"
    sections = ["What", "Files Affected", "Constraints"]
    result = n.apply_known_file_paths(body, {}, sections=sections)
    assert "## Files Affected\nUnknown\n\n## Constraints\nnone" in result


def test_apply_known_file_paths_handles_last_section_in_body():
    body = "## What\ntext\n\n## Files Affected\n- `old.py`\n"
    hints = {"old": ["real/old.py"]}
    result = n.apply_known_file_paths(body, hints)
    assert "- `real/old.py`" in result
