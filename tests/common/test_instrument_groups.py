import json

import pytest

from backend.common import instrument_groups


def test_normalise_filters_and_sorts(monkeypatch, tmp_path):
    monkeypatch.setattr(instrument_groups.config, "data_root", tmp_path)

    values = [
        " Foo ",
        "foo",
        "BAR",
        "baz",
        None,
        "",
        "   ",
        "BaR",
        123,
        "baz",
    ]

    assert instrument_groups._normalise(values) == ["BAR", "baz", "Foo"]


def test_load_groups_handles_formats(monkeypatch, tmp_path):
    monkeypatch.setattr(instrument_groups.config, "data_root", tmp_path)

    groups_path = tmp_path / "instrument-groups.json"

    groups_path.write_text(json.dumps(["  beta", "Alpha", "alpha "]), encoding="utf-8")
    assert instrument_groups.load_groups() == ["Alpha", "beta"]

    groups_path.write_text(
        json.dumps({"groups": ["  beta", "Alpha", "alpha "]}),
        encoding="utf-8",
    )
    assert instrument_groups.load_groups() == ["Alpha", "beta"]

    groups_path.unlink()
    assert instrument_groups.load_groups() == []

    groups_path.write_text("{", encoding="utf-8")
    assert instrument_groups.load_groups() == []


def test_save_and_add_group_behaviour(monkeypatch, tmp_path):
    monkeypatch.setattr(instrument_groups.config, "data_root", tmp_path)

    saved_path = instrument_groups.save_groups(["  beta  ", "Alpha", "alpha "])
    assert saved_path == tmp_path / "instrument-groups.json"
    saved_values = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved_values == ["Alpha", "beta"]

    assert instrument_groups.add_group("Gamma") == ["Alpha", "beta", "Gamma"]
    assert instrument_groups.add_group(" gamma ") == ["Alpha", "beta", "Gamma"]

    with pytest.raises(TypeError):
        instrument_groups.add_group(123)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        instrument_groups.add_group("   ")
