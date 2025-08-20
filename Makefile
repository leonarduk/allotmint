.PHONY: format lint

format:
	isort --sp backend/pyproject.toml backend tests
	black --config backend/pyproject.toml backend tests

lint:
	ruff check --config backend/pyproject.toml backend tests
	black --check --config backend/pyproject.toml backend tests
	pytest
