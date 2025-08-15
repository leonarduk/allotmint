from pathlib import Path


root = Path(__file__).resolve().parent.parent


def test_stylesheet_snapshot():
    css = (root / "frontend/src/index.css").read_text()
    expected = (root / "tests/snapshots/index.css").read_text()
    assert css == expected
