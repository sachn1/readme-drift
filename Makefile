.PHONY: check

check:
	poetry run ruff check .
	poetry run ruff format --check .
	poetry run pytest --cov=readme_drift --cov-fail-under=80
