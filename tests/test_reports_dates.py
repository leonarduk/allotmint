from datetime import date
from pathlib import Path

import backend.reports as reports


def test_parse_date_valid():
    assert reports._parse_date("2024-05-06") == date(2024, 5, 6)


def test_parse_date_invalid():
    assert reports._parse_date("not-a-date") is None


def test_transaction_roots_aws(monkeypatch):
    monkeypatch.setattr(reports.config, "app_env", "aws")
    assert list(reports._transaction_roots()) == ["transactions"]


def test_transaction_roots_local(monkeypatch):
    monkeypatch.setattr(reports.config, "app_env", "local")
    monkeypatch.setattr(reports.config, "transactions_output_root", Path("/existing"))
    monkeypatch.setattr(reports.config, "accounts_root", Path("/missing"))
    monkeypatch.setattr(reports.config, "data_root", Path("/data"))

    exists_map = {
        Path("/existing"): True,
        Path("/missing"): False,
        Path("/data/transactions"): True,
    }

    def fake_exists(self):
        return exists_map.get(self, False)

    monkeypatch.setattr(Path, "exists", fake_exists)

    roots = list(reports._transaction_roots())
    assert roots == ["/existing", "/data/transactions"]
    assert len(roots) == len(set(roots))
