import json
from pathlib import Path

import pytest

from backend.routes import query


@pytest.mark.anyio
async def test_list_saved_queries_returns_rich_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved_dir = tmp_path / "queries"
    saved_dir.mkdir()

    (saved_dir / "alpha.json").write_text(
        json.dumps(
            {
                "name": "Alpha Query",
                "start": "2024-01-01",
                "end": "2024-01-31",
                "tickers": ["AAA"],
                "metrics": ["var"],
            }
        )
    )
    (saved_dir / "beta.json").write_text(
        json.dumps(
            {
                "start": "2023-12-01",
                "owners": ["Jane"],
                "metrics": ["meta"],
            }
        )
    )

    monkeypatch.setattr(query, "QUERIES_DIR", saved_dir)
    monkeypatch.setattr(query.config, "app_env", "local", raising=False)

    results = await query.list_saved_queries()

    assert results == [
        {
            "id": "alpha",
            "name": "Alpha Query",
            "params": {
                "start": "2024-01-01",
                "end": "2024-01-31",
                "tickers": ["AAA"],
                "metrics": ["var"],
            },
        },
        {
            "id": "beta",
            "name": "beta",
            "params": {
                "start": "2023-12-01",
                "owners": ["Jane"],
                "metrics": ["meta"],
            },
        },
    ]


@pytest.mark.anyio
async def test_list_saved_queries_returns_empty_when_missing_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(query, "QUERIES_DIR", tmp_path / "queries")
    monkeypatch.setattr(query.config, "app_env", None, raising=False)

    assert await query.list_saved_queries() == []
