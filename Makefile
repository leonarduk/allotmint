.PHONY: format lint local-up local-down lambda-up lambda-down lambda-test lambda-test-price lambda-test-trading

format:
	isort --sp backend/pyproject.toml backend tests
	black --config backend/pyproject.toml backend tests

lint:
	ruff check --config backend/pyproject.toml backend tests
	black --check --config backend/pyproject.toml backend tests
	pytest


local-up:
	docker compose -f docker-compose.local.yml --env-file .env.local up --build

local-down:
	docker compose -f docker-compose.local.yml --env-file .env.local down --remove-orphans

# ── Local Lambda test harness ──────────────────────────────────────────────
# Requires Docker. Copy .env.lambda.example to .env.lambda before first use.

lambda-up:
	docker compose -f docker-compose.lambda.yml --env-file .env.lambda up --build -d

lambda-down:
	docker compose -f docker-compose.lambda.yml --env-file .env.lambda down --remove-orphans

lambda-test:
	curl -s -XPOST "http://localhost:9010/2015-03-31/functions/function/invocations" \
		-H "Content-Type: application/json" \
		-d @tests/integration/payloads/api_http_event.json | python -m json.tool

lambda-test-price:
	curl -s -XPOST "http://localhost:9011/2015-03-31/functions/function/invocations" \
		-H "Content-Type: application/json" \
		-d @tests/integration/payloads/scheduled_event.json | python -m json.tool

lambda-test-trading:
	curl -s -XPOST "http://localhost:9012/2015-03-31/functions/function/invocations" \
		-H "Content-Type: application/json" \
		-d @tests/integration/payloads/scheduled_event.json | python -m json.tool
