.PHONY: install dev test lint format typecheck build clean ci

install:
	pip install .

dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --cov=codesentinel --cov-report=term-missing

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/codesentinel/

build:
	hatch build

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +

ci: lint typecheck test
