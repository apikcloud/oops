# Makefile for oops project
# Requires Python >=3.8, pip, pytest, ruff installed in your venv.

.PHONY: help install lint typecheck test cov cov-html clean build

# Default target
help:
	@echo "Usage:"
	@echo "  make install      Install package in editable mode"
	@echo "  make lint         Run ruff linter"
	@echo "  make typecheck    Run pyright type checking"
	@echo "  make test         Run pytest suite"
	@echo "  make cov          Run pytest with coverage"
	@echo "  make cov-html     Run pytest with coverage"
	@echo "  make build        Build wheel/sdist"
	@echo "  make clean        Remove build artifacts"

install:
	pip install -e .[dev] --break-system-packages

lint:
	ruff check .

typecheck:
	pyright || true

test:
	pytest -vv

cov:
	pytest --cov=oops --cov-branch --cov-report=term-missing

cov-html:
	pytest --cov=oops --cov-branch --cov-report=html
	@echo "Open htmlcov/index.html"

build:
	python -m build

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache .pyright
