import backend.common.data_loader as dl
from pathlib import Path


def test_resolve_paths_accepts_windows_accounts_root(monkeypatch):
    win_path = Path("C:/accounts")

    orig_exists = Path.exists

    def fake_exists(self):
        if str(self) == str(win_path):
            return True
        return orig_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(dl.config, "accounts_root", win_path)

    paths = dl.resolve_paths(dl.config.repo_root, dl.config.accounts_root)
    assert paths.accounts_root == win_path
