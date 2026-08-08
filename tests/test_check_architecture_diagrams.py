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

    stale, unreadable = find_stale_legacy_references(tmp_path, [guide, readme])

    assert stale == [guide]
    assert unreadable == []


def test_legacy_reference_is_not_stale_while_diagram_exists(tmp_path: Path) -> None:
    diagram = Path(LEGACY_DIAGRAM)
    guide = Path("docs/deploy.md")
    (tmp_path / "docs").mkdir()
    (tmp_path / diagram).write_text("<svg/>", encoding="utf-8")
    (tmp_path / guide).write_text(str(diagram), encoding="utf-8")

    stale, unreadable = find_stale_legacy_references(tmp_path, [diagram, guide])

    assert stale == []
    assert unreadable == []


def test_sibling_relative_legacy_reference_is_detected(tmp_path: Path) -> None:
    guide = Path("docs/deploy.md")
    (tmp_path / "docs").mkdir()
    (tmp_path / guide).write_text("See ./aws-architecture.svg for context", encoding="utf-8")

    stale, unreadable = find_stale_legacy_references(tmp_path, [guide])

    assert stale == [guide]
    assert unreadable == []


def test_bare_filename_outside_docs_is_not_a_sibling_match(tmp_path: Path) -> None:
    notes = Path("frontend/notes.md")
    (tmp_path / "frontend").mkdir()
    (tmp_path / notes).write_text("See aws-architecture.svg for context", encoding="utf-8")

    stale, unreadable = find_stale_legacy_references(tmp_path, [notes])

    assert stale == []
    assert unreadable == []


def test_unreadable_candidate_is_reported_not_silently_skipped(tmp_path: Path) -> None:
    guide = Path("docs/deploy.md")
    (tmp_path / "docs").mkdir()
    (tmp_path / guide).write_bytes(b"\xff\xfe\x00 not valid utf-8")

    stale, unreadable = find_stale_legacy_references(tmp_path, [guide])

    assert stale == []
    assert unreadable == [guide]


def test_known_binary_formats_are_skipped_without_being_reported(tmp_path: Path) -> None:
    image = Path("docs/diagram.png")
    (tmp_path / "docs").mkdir()
    (tmp_path / image).write_bytes(b"\x89PNG\r\n\x1a\n not valid utf-8")

    stale, unreadable = find_stale_legacy_references(tmp_path, [image])

    assert stale == []
    assert unreadable == []
