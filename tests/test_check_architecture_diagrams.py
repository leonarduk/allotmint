from pathlib import Path

from scripts.check_architecture_diagrams import (
    LEGACY_DIAGRAM,
    find_stale_legacy_references,
    find_unreproducible_diagrams,
)


def test_architecture_svg_without_generator_is_reported() -> None:
    files = [Path("docs/cloud-architecture.svg")]

    assert find_unreproducible_diagrams(files) == files


def test_matching_generator_makes_architecture_svg_reproducible() -> None:
    files = [
        Path("docs/cloud-architecture.svg"),
        Path("scripts/generate_cloud_architecture.py"),
    ]

    assert find_unreproducible_diagrams(files) == []


def test_non_architecture_svg_does_not_require_generator() -> None:
    files = [Path("frontend/public/logo.svg")]

    assert find_unreproducible_diagrams(files) == []


def test_stale_legacy_reference_is_reported_outside_readmes(tmp_path: Path) -> None:
    guide = Path("docs/deploy.md")
    readme = Path("docs/README.md")
    (tmp_path / "docs").mkdir()
    (tmp_path / guide).write_text(f"See {LEGACY_DIAGRAM}", encoding="utf-8")
    (tmp_path / readme).write_text(f"See {LEGACY_DIAGRAM}", encoding="utf-8")

    assert find_stale_legacy_references(tmp_path, [guide, readme]) == [guide]


def test_legacy_reference_is_not_stale_while_diagram_exists(tmp_path: Path) -> None:
    diagram = Path(LEGACY_DIAGRAM)
    guide = Path("docs/deploy.md")
    (tmp_path / "docs").mkdir()
    (tmp_path / diagram).write_text("<svg/>", encoding="utf-8")
    (tmp_path / guide).write_text(str(diagram), encoding="utf-8")

    assert find_stale_legacy_references(tmp_path, [diagram, guide]) == []
