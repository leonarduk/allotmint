from pathlib import Path

root = Path(__file__).resolve().parent.parent


def test_stylesheet_snapshot():
    css = (root / "frontend/src/index.css").read_text()
    expected = (root / "tests/snapshots/index.css").read_text()
    assert css == expected, (
        "frontend/src/index.css differs from tests/snapshots/index.css. If the "
        "CSS change is intentional, copy frontend/src/index.css over the snapshot."
    )
