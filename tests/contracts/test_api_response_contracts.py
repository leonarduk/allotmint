from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app

SCHEMA_BUNDLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "contracts"
    / "generated"
    / "api-contract-schemas.v1.json"
)
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "contracts" / "fixtures"
CONTRACT_VERSION = "v1"


def _load_schema_bundle() -> dict[str, Any]:
    return json.loads(SCHEMA_BUNDLE_PATH.read_text(encoding="utf-8"))


def _load_fixture(name: str) -> Any:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


SCHEMA_BUNDLE = _load_schema_bundle()
ENDPOINT_CONTRACTS: dict[str, dict[str, Any]] = SCHEMA_BUNDLE["endpoints"]
ENDPOINT_FIXTURES = {
    "config": "config.v1.json",
    "owners": "owners.v1.json",
    "groups": "groups.v1.json",
    "groupPortfolio": "groupPortfolio.v1.json",
    "portfolio": "portfolio.v1.json",
    "transactions": "transactions.v1.json",
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _validate_contract(name: str, payload: Any) -> list[str]:
    validator = Draft202012Validator(ENDPOINT_CONTRACTS[name]["schema"])
    return [error.message for error in validator.iter_errors(payload)]


def _assert_matches_contract(name: str, payload: Any) -> None:
    errors = _validate_contract(name, payload)
    assert errors == [], f"{name} schema errors: {errors}"


@pytest.mark.parametrize(
    ("name", "path"),
    [(name, spec["path"]) for name, spec in ENDPOINT_CONTRACTS.items()],
)
def test_live_endpoints_match_versioned_contract_schema(client: TestClient, name: str, path: str) -> None:
    response = client.get(path)

    assert SCHEMA_BUNDLE["version"] == CONTRACT_VERSION
    assert response.status_code == 200
    _assert_matches_contract(name, response.json())


@pytest.mark.parametrize("name", sorted(ENDPOINT_FIXTURES))
def test_examples_remain_valid_examples_but_not_authority(name: str) -> None:
    fixture = _load_fixture(ENDPOINT_FIXTURES[name])
    _assert_matches_contract(name, fixture)


def test_schema_rejects_required_field_removal(client: TestClient) -> None:
    response = client.get("/portfolio/alice")
    payload = response.json()
    payload.pop("owner", None)

    errors = _validate_contract("portfolio", payload)

    assert errors
    assert any("owner" in error for error in errors)


def test_schema_rejects_field_type_drift(client: TestClient) -> None:
    response = client.get("/owners")
    payload = response.json()
    if not payload:
        pytest.skip("owners endpoint returned no rows")
    payload[0]["has_transactions_artifact"] = "false"

    errors = _validate_contract("owners", payload)

    assert errors
    assert any("boolean" in error for error in errors)


def test_schema_allows_optional_field_evolution_and_key_reordering(client: TestClient) -> None:
    response = client.get("/owners")
    payload = response.json()
    if not payload:
        pytest.skip("owners endpoint returned no rows")

    evolved = deepcopy(payload)
    evolved[0]["email"] = "alice@example.com"
    reordered_first = dict(reversed(list(evolved[0].items())))
    evolved[0] = reordered_first

    _assert_matches_contract("owners", evolved)


def test_contract_examples_are_not_used_as_exact_snapshots(client: TestClient) -> None:
    response = client.get("/owners")
    payload = response.json()
    fixture = _load_fixture("owners.v1.json")

    assert payload != fixture
    _assert_matches_contract("owners", payload)
    _assert_matches_contract("owners", fixture)
