from pathlib import Path


def test_stylesheet_snapshot():
    css = Path("frontend/src/index.css").read_text()
    expected = Path("tests/snapshots/index.css").read_text()
    assert css == expected
