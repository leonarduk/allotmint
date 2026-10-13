from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app import create_app
from backend.routes import transactions as transactions_routes

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


# The committed demo data has no transaction files, so a live ``GET
# /transactions`` returned ``[]`` and validated against any item schema -
# which is how #10752 (realised-gain fields stripped by the frontend
# contract) got through. Seed a BUY+SELL pair for a test-only owner and run it
# through the real ``_transactions_from_doc`` so the SELL carries the derived
# Section 104 fields exactly as the route emits them (#10772).
CONTRACT_SEED_OWNER = "contract-seed"
CONTRACT_SEED_ACCOUNT = "isa"
CONTRACT_SEED_TRANSACTIONS_DOC: dict[str, Any] = {
    "owner": CONTRACT_SEED_OWNER,
    "account_type": CONTRACT_SEED_ACCOUNT,
    "transactions": [
        {"date": "2024-01-02", "type": "BUY", "ticker": "VWRL.L", "units": 10, "price_gbp": 100.0, "fees": 0.0},
        {"date": "2024-06-03", "type": "SELL", "ticker": "VWRL.L", "units": 4, "price_gbp": 150.0, "fees": 0.0},
    ],
}


# Matches ``load_all_transactions(store=None)``; ``GET /transactions`` applies
# its owner/account/type/date filters to the result, so they still run.
def _seeded_transactions(store: Any = None) -> list[transactions_routes.Transaction]:
    return transactions_routes._transactions_from_doc(
        CONTRACT_SEED_OWNER, CONTRACT_SEED_ACCOUNT, CONTRACT_SEED_TRANSACTIONS_DOC
    )


@pytest.fixture(scope="module")
def client() -> TestClient:
    # Use as a context manager so the app's lifespan startup runs (it warms
    # the in-memory price snapshot from the committed seed file). Without
    # this, requests fall through to raw timeseries lookups that can surface
    # stale/incomplete rows for the current trading day - see issue #5192.
    # The seed replaces the transactions loader for every test in this module;
    # nothing here needs the real (empty) committed transaction data.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(transactions_routes, "load_all_transactions", _seeded_transactions)
        with TestClient(create_app()) as test_client:
            yield test_client


def _validate_contract(name: str, payload: Any) -> list[str]:
    validator = Draft202012Validator(ENDPOINT_CONTRACTS[name]["schema"])
    return [error.message for error in validator.iter_errors(payload)]


def _assert_matches_contract(name: str, payload: Any) -> None:
    errors = _validate_contract(name, payload)
    assert errors == [], f"{name} schema errors: {errors}"


def _assert_non_vacuous(name: str, payload: Any) -> None:
    """Fail when ``payload`` is too thin for schema validation to mean anything.

    An empty array validates against any ``items`` schema, and an account
    without holdings never exercises the holding schema (#10772).
    """
    assert payload, f"{name} returned an empty payload; the contract check would be vacuous"
    if isinstance(payload, list):
        assert all(isinstance(row, dict) and row for row in payload), f"{name} returned empty rows"
    if name in {"portfolio", "groupPortfolio"}:
        assert isinstance(payload, dict), f"{name} should be an object, got {type(payload).__name__}"
        accounts = payload.get("accounts") or []
        assert any(account.get("holdings") for account in accounts), f"{name} has no account with holdings"


def _without_transaction_property(field: str) -> dict[str, Any]:
    schema = deepcopy(ENDPOINT_CONTRACTS["transactions"]["schema"])
    item_schema = schema["items"]
    assert item_schema.get("additionalProperties") is False
    del item_schema["properties"][field]
    if field in item_schema.get("required", []):
        item_schema["required"].remove(field)
    return schema


@pytest.mark.parametrize(
    ("name", "path"),
    [(name, spec["path"]) for name, spec in ENDPOINT_CONTRACTS.items()],
)
def test_live_endpoints_match_versioned_contract_schema(client: TestClient, name: str, path: str) -> None:
    response = client.get(path)

    assert SCHEMA_BUNDLE["version"] == CONTRACT_VERSION
    assert response.status_code == 200
    payload = response.json()
    _assert_non_vacuous(name, payload)
    _assert_matches_contract(name, payload)


def test_live_transactions_payload_carries_realised_gain_fields(client: TestClient) -> None:
    response = client.get("/transactions")
    assert response.status_code == 200

    sells = [row for row in response.json() if row.get("type") == "SELL"]
    assert sells, "seeded SELL missing from /transactions"
    # Section 104 pool: 10 units at 100, so selling 4 at 150 costs 4 x 100 = 400
    # against proceeds of 600. The seed has no same-day trades, so the pool
    # average is the only matching rule applied.
    assert sells[0]["cost_basis_gbp"] == pytest.approx(400.0)
    assert sells[0]["proceeds_gbp"] == pytest.approx(600.0)
    assert sells[0]["realised_gain_gbp"] == pytest.approx(200.0)
    assert sells[0]["unmatched_units"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("owners", []),
        ("owners", [{}]),
        ("portfolio", {"owner": "x", "accounts": [{"holdings": []}]}),
        ("groupPortfolio", {"slug": "all", "accounts": []}),
    ],
)
def test_non_vacuous_guard_rejects_thin_payloads(name: str, payload: Any) -> None:
    with pytest.raises(AssertionError):
        _assert_non_vacuous(name, payload)


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("owners", [{"owner": "x"}]),
        ("portfolio", {"owner": "x", "accounts": [{"holdings": []}, {"holdings": [{"ticker": "X"}]}]}),
    ],
)
def test_non_vacuous_guard_accepts_populated_payloads(name: str, payload: Any) -> None:
    _assert_non_vacuous(name, payload)


@pytest.mark.parametrize("field", ["realised_gain_gbp", "cost_basis_gbp", "proceeds_gbp", "unmatched_units"])
def test_transactions_contract_drift_is_detected(client: TestClient, field: str) -> None:
    """Dropping a backend-emitted field from the frontend contract must fail validation.

    Guards against the live check going vacuous again (#10752, #10772).
    """
    payload = client.get("/transactions").json()
    validator = Draft202012Validator(_without_transaction_property(field))

    drift_errors = [
        error
        for error in validator.iter_errors(payload)
        if error.validator == "additionalProperties" and field in error.message
    ]

    assert drift_errors, f"removing {field} from the contract did not fail validation"


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
    _assert_non_vacuous("owners", payload)
    payload[0]["has_transactions_artifact"] = "false"

    errors = _validate_contract("owners", payload)

    assert errors
    assert any("boolean" in error for error in errors)


def test_schema_allows_optional_field_evolution_and_key_reordering(client: TestClient) -> None:
    response = client.get("/owners")
    payload = response.json()
    _assert_non_vacuous("owners", payload)

    # ``email`` is a declared optional property (apiContracts.ts); undeclared
    # keys are rejected by ``additionalProperties: false``.
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
