import backend.common.portfolio as portfolio


def test_list_owners_skips_bad_json(tmp_path, caplog):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "person.json").write_text("{bad json")

    with caplog.at_level("WARNING"):
        owners = portfolio.list_owners(accounts_root=tmp_path)

    assert owners == []
    assert "Skipping owner file" in caplog.text
