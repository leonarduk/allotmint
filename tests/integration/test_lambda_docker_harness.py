from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_repo_file(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_lambda_compose_defines_local_runtime_dependencies() -> None:
    compose = read_repo_file("docker-compose.lambda.yml")

    assert "lambda-backend:" in compose
    assert "dockerfile: backend/Dockerfile.lambda" in compose
    assert "dynamodb-local:" in compose
    assert "amazon/dynamodb-local" in compose
    assert "AWS_ENDPOINT_URL_DYNAMODB" in compose
    assert "AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-dummy}" in compose
    assert "DATA_BUCKET: ${DATA_BUCKET:-local-lambda-data}" in compose


def test_lambda_harness_uses_production_lambda_python_image() -> None:
    dockerfile = read_repo_file("backend/Dockerfile.lambda")
    compose = read_repo_file("docker-compose.lambda.yml")
    cdk_stack = read_repo_file("cdk/stacks/backend_lambda_stack.py")

    image_match = re.search(r"^FROM public\.ecr\.aws/lambda/python:(\d+\.\d+)$", dockerfile, re.MULTILINE)
    assert image_match is not None
    assert image_match.group(1) == "3.12"
    assert "dockerfile: backend/Dockerfile.lambda" in compose
    assert 'file="backend/Dockerfile.lambda"' in cdk_stack


def test_lambda_make_target_and_script_reference_default_fixture_pair() -> None:
    makefile = read_repo_file("Makefile")
    script = read_repo_file("scripts/bash/lambda-test.sh")

    assert ".PHONY: format lint local-up local-down lambda-test" in makefile
    assert "lambda-test:\n\tbash scripts/bash/lambda-test.sh" in makefile
    assert "tests/integration/lambda/payloads/http-health-v2.json" in script
    assert "tests/integration/lambda/expected/http-health-v2.json" in script
    assert "/2015-03-31/functions/function/invocations" in script


def test_lambda_health_fixture_matches_expected_local_environment() -> None:
    payload = json.loads(read_repo_file("tests/integration/lambda/payloads/http-health-v2.json"))
    expected = json.loads(read_repo_file("tests/integration/lambda/expected/http-health-v2.json"))

    assert payload["version"] == "2.0"
    assert payload["rawPath"] == "/health"
    assert payload["requestContext"]["http"]["method"] == "GET"
    assert expected == {"statusCode": 200, "body": {"status": "ok", "env": "local"}}


def test_scheduled_lambda_sample_payloads_are_available() -> None:
    payload_dir = ROOT / "tests/integration/lambda/payloads"

    for name in ("price-refresh-event.json", "trading-agent-event.json"):
        payload = json.loads((payload_dir / name).read_text(encoding="utf-8"))
        assert payload["source"] == "allotmint.local"
        assert payload["detail-type"] == "Scheduled Event"


def test_trading_agent_expected_response_fixture_is_available() -> None:
    expected = json.loads(read_repo_file("tests/integration/lambda/expected/trading-agent-event.json"))

    assert expected == {"status": "ok"}
