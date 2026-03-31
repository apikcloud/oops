# Makefile for oops project
# Requires Python >=3.7 and pip. All dev tools are installed via: make install

.PHONY: help install install-docs lint typecheck test cov cov-html clean build docs docs-serve

# Default target
help:
	@echo "Usage:"
	@echo "  make install      Install package in editable mode"
	@echo "  make lint         Run ruff linter"
	@echo "  make typecheck    Run pyright type checking"
	@echo "  make test         Run pytest suite"
	@echo "  make cov          Run pytest with coverage"
	@echo "  make cov-html     Run pytest with coverage (HTML)"
	@echo "  make install-docs Install docs dependencies"
	@echo "  make build        Build wheel/sdist"
	@echo "  make docs         Build documentation site"
	@echo "  make docs-serve   Reinstall + serve docs with live-reload"
	@echo "  make clean        Remove build artifacts"

install:
	python3 -m pip install -e .[dev]

install-docs:
	python3 -m pip install -e .[docs]

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

docs-serve: install
	mkdocs serve --watch oops/

clean:
	rm -rf build dist site *.egg-info .pytest_cache .ruff_cache .mypy_cache .pyright
