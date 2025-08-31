import backend.common.data_loader as dl


def test_load_account_local(tmp_path):
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    (owner_dir / "gia.json").write_text('{"balance": 5}')
    data = dl.load_account("alice", "gia", data_root=tmp_path)
    assert data == {"balance": 5}
