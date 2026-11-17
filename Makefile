.PHONY: lint test check cards

lint:
	poetry run ruff check .
	poetry run ruff format --check .

test:
	poetry run pytest --cov=readme_drift --cov-fail-under=80

check: lint test

cards:
	poetry run python tests/scenario_cards.py
