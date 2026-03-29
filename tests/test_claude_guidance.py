from pathlib import Path


CLAUDE_PATH = Path(__file__).parent.parent / "CLAUDE.md"


def _claude_text() -> str:
    return CLAUDE_PATH.read_text(encoding="utf-8")


def test_claude_has_cdk_infrastructure_section() -> None:
    text = _claude_text()
    assert "### CDK / Infrastructure" in text


def test_claude_has_read_before_writing_rules() -> None:
    text = _claude_text()
    assert "read the full current content of every file you plan to change" in text
    assert (
        "read the current file content in full from disk before writing; do not rely on diff snippets"
        in text
    )


def test_claude_requires_handler_trace_evidence_for_iam_changes() -> None:
    text = _claude_text()
    assert "full call chain" in text
    assert "cite specific `file:function` references" in text
