# Makefile for oops project
# Requires Python >=3.7, pip, pytest, ruff installed in your venv.

.PHONY: help install install-docs lint typecheck test cov cov-html clean build docs docs-serve

# Default target
help:
	@echo "Usage:"
	@echo "  make install      Install package in editable mode"
	@echo "  make lint         Run ruff linter"
	@echo "  make typecheck    Run pyright type checking"
	@echo "  make test         Run pytest suite"
	@echo "  make cov          Run pytest with coverage"
	@echo "  make cov-html     Run pytest with coverage"
	@echo "  make install-docs Install docs dependencies"
	@echo "  make build        Build wheel/sdist"
	@echo "  make docs         Build documentation site"
	@echo "  make docs-serve   Reinstall + serve docs with live-reload"
	@echo "  make clean        Remove build artifacts"

install:
	pip install -e .[dev] --break-system-packages

install-docs:
	pip install -e .[docs] --break-system-packages

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

docs:
	mkdocs build

docs-serve:
	pip install -e . --break-system-packages -q && mkdocs serve --watch oops/

clean:
	rm -rf build dist site *.egg-info .pytest_cache .ruff_cache .mypy_cache .pyright
