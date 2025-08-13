import pytest

from backend.common import instruments


def test_missing_file_returns_empty(monkeypatch, tmp_path):
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(instruments, "_instrument_path", lambda t: missing)
    assert instruments.get_instrument_meta("DOES.NOTEXIST") == {}


def test_invalid_json_returns_empty(monkeypatch, tmp_path, caplog):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    monkeypatch.setattr(instruments, "_instrument_path", lambda t: bad)
    with caplog.at_level("WARNING"):
        assert instruments.get_instrument_meta("BAD.JSON") == {}
    assert "Invalid instrument JSON" in caplog.text


def test_unexpected_error_propagates(monkeypatch, tmp_path, caplog):
    path = tmp_path / "ok.json"
    path.write_text("{}")
    monkeypatch.setattr(instruments, "_instrument_path", lambda t: path)

    def boom(fp):
        raise RuntimeError("boom")

    monkeypatch.setattr(instruments.json, "load", boom)

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError):
            instruments.get_instrument_meta("ERR.TKR")
    assert "Unexpected error loading" in caplog.text

