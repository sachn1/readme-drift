.PHONY: lint test check

lint:
	poetry run ruff check .
	poetry run ruff format --check .

test:
	poetry run pytest --cov=readme_drift --cov-fail-under=80

check: lint test
