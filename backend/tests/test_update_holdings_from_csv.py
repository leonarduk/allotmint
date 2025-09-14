from types import SimpleNamespace

from backend.utils import update_holdings_from_csv


def test_update_from_csv_returns_case_sensitive_path(monkeypatch, tmp_path):
    monkeypatch.setattr(
        update_holdings_from_csv, "config", SimpleNamespace(accounts_root=tmp_path)
    )
    monkeypatch.setattr(
        update_holdings_from_csv,
        "importers",
        SimpleNamespace(parse=lambda provider, data: []),
    )
    monkeypatch.setattr(
        update_holdings_from_csv,
        "portfolio_loader",
        SimpleNamespace(rebuild_account_holdings=lambda *a, **k: None),
    )

    path = update_holdings_from_csv.update_from_csv("Alice", "ISA", "dummy", b"")

    expected = tmp_path / "Alice" / "ISA.json"
    assert path == str(expected)
    assert expected.exists()
