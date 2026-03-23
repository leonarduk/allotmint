import json

import backend.common.data_loader as dl


def test_load_account_local(tmp_path):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "gia.json").write_text('{"balance": 5}')
    data = dl.load_account("alice", "gia", data_root=tmp_path)
    assert data == {"balance": 5}


def test_list_local_plots_filters_special_directories(tmp_path, monkeypatch):
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "demo.json").write_text("{}")

    idea = tmp_path / ".idea"
    idea.mkdir()
    (idea / "junk.json").write_text("{}")

    alice = tmp_path / "alice"
    alice.mkdir()
    (alice / "isa.json").write_text("{}")

    monkeypatch.setattr(dl.config, "disable_auth", True, raising=False)

    owners = dl._list_local_plots(data_root=tmp_path, current_user=None)
    assert owners == [
        {"owner": "alice", "accounts": ["isa"]},
    ]
    assert all("full_name" not in entry for entry in owners)
    assert all(entry["owner"] not in {"demo", ".idea"} for entry in owners)


def test_list_local_plots_authenticated(tmp_path, monkeypatch):
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "demo.json").write_text("{}")

    alice = tmp_path / "alice"
    alice.mkdir()
    (alice / "isa.json").write_text("{}")
    # alice grants viewing rights to bob via her person.json
    (alice / "person.json").write_text(json.dumps({"viewers": ["bob"]}))

    bob = tmp_path / "bob"
    bob.mkdir()
    (bob / "gia.json").write_text("{}")
    # bob has no extra viewers; he can only see his own account
    (bob / "person.json").write_text(json.dumps({"viewers": []}))

    monkeypatch.setattr(dl.config, "disable_auth", False, raising=False)

    owners = dl._list_local_plots(data_root=tmp_path, current_user="bob")
    assert owners == [
        {"owner": "alice", "accounts": ["isa"]},
        {"owner": "bob", "accounts": ["gia"]},
    ]
    assert all("full_name" not in entry for entry in owners)
