import json

import backend.common.portfolio as portfolio


def test_list_owners_skips_bad_json(tmp_path, caplog):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "person.json").write_text("{bad json")

    with caplog.at_level("WARNING"):
        owners = portfolio.list_owners(accounts_root=tmp_path)

    assert owners == []
    assert "Skipping owner file" in caplog.text


def test_list_owners_filters_by_viewer(tmp_path):
    alice = tmp_path / "alice"
    alice.mkdir()
    (alice / "person.json").write_text(
        json.dumps({"owner": "alice", "viewers": ["bob"]})
    )
    bob = tmp_path / "bob"
    bob.mkdir()
    (bob / "person.json").write_text(json.dumps({"owner": "bob"}))

    owners = portfolio.list_owners(accounts_root=tmp_path, current_user="bob")
    assert set(owners) == {"alice", "bob"}
