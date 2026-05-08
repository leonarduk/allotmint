.PHONY: format lint local-up local-down lambda-test

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

lambda-test:
	bash scripts/bash/lambda-test.sh
