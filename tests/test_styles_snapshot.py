from pathlib import Path


def test_stylesheet_snapshot():
    css = Path("frontend/src/styles.css").read_text()
    expected = Path("tests/snapshots/styles.css").read_text()
    assert css == expected
