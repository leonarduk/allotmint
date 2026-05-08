.PHONY: format lint local-up local-down

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

PYTHON ?= python3
LAMBDA_INTEGRATION_DIR := tests/integration
LAMBDA_ACTUAL_DIR := $(LAMBDA_INTEGRATION_DIR)/actual

.PHONY: lambda-test lambda-test-api lambda-test-price-refresh lambda-test-trading-agent

lambda-test: lambda-test-api lambda-test-price-refresh lambda-test-trading-agent

lambda-test-api:
	mkdir -p $(LAMBDA_ACTUAL_DIR)
	$(PYTHON) -m tests.integration.invoke_lambda api-http $(LAMBDA_INTEGRATION_DIR)/payloads/api_http_event.json > $(LAMBDA_ACTUAL_DIR)/api_http_response.json
	jq -e --slurpfile expected $(LAMBDA_INTEGRATION_DIR)/expected/api_http_response.json '.statusCode == $$expected[0].statusCode' $(LAMBDA_ACTUAL_DIR)/api_http_response.json

lambda-test-price-refresh:
	mkdir -p $(LAMBDA_ACTUAL_DIR)
	$(PYTHON) -m tests.integration.invoke_lambda price-refresh $(LAMBDA_INTEGRATION_DIR)/payloads/price_refresh_event.json > $(LAMBDA_ACTUAL_DIR)/price_refresh_response.json
	jq -e --slurpfile expected $(LAMBDA_INTEGRATION_DIR)/expected/price_refresh_response.json '.statusCode == $$expected[0].statusCode' $(LAMBDA_ACTUAL_DIR)/price_refresh_response.json

lambda-test-trading-agent:
	mkdir -p $(LAMBDA_ACTUAL_DIR)
	$(PYTHON) -m tests.integration.invoke_lambda trading-agent $(LAMBDA_INTEGRATION_DIR)/payloads/trading_agent_event.json > $(LAMBDA_ACTUAL_DIR)/trading_agent_response.json
	jq -e --slurpfile expected $(LAMBDA_INTEGRATION_DIR)/expected/trading_agent_response.json '.statusCode == $$expected[0].statusCode' $(LAMBDA_ACTUAL_DIR)/trading_agent_response.json
