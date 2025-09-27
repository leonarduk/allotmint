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
    assert all(entry["owner"] not in {"demo", ".idea"} for entry in owners)


def test_list_local_plots_authenticated(tmp_path, monkeypatch):
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "demo.json").write_text("{}")

    alice = tmp_path / "alice"
    alice.mkdir()
    (alice / "isa.json").write_text("{}")

    bob = tmp_path / "bob"
    bob.mkdir()
    (bob / "gia.json").write_text("{}")

    monkeypatch.setattr(dl.config, "disable_auth", False, raising=False)

    # Emulate per-owner metadata so that ``alice`` grants viewing rights to
    # ``bob`` while ``bob`` has no additional viewers.
    def fake_meta(owner, root=None):
        if owner == "alice":
            return {"viewers": ["bob"]}
        return {}

    monkeypatch.setattr(dl, "load_person_meta", fake_meta)

    owners = dl._list_local_plots(data_root=tmp_path, current_user="bob")
    assert owners == [
        {"owner": "alice", "accounts": ["isa"]},
        {"owner": "bob", "accounts": ["gia"]},
    ]
