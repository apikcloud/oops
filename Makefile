# Makefile for oops project
# Requires Python >=3.7 and uv. All dev tools are installed via: make install

.PHONY: help install install-docs install-gui lint typecheck test cov cov-html clean build docs docs-serve

# Default target
help:
	@echo "Usage:"
	@echo "  make install      Install package in editable mode"
	@echo "  make install-docs Install docs dependencies"
	@echo "  make install-gui  Install GUI (pywebview) dependencies"
	@echo "  make build        Build wheel/sdist"
	@echo "  make build-ui     Build UI"
	@echo "  make clean        Remove build artifacts"
	@echo "  make cov          Run pytest with coverage"
	@echo "  make cov-html     Run pytest with coverage (HTML)"
	@echo "  make docs         Build documentation site"
	@echo "  make docs-serve   Reinstall + serve docs with live-reload"
	@echo "  make lint         Run ruff linter"
	@echo "  make test         Run pytest suite"
	@echo "  make typecheck    Run pyright type checking"

install:
	uv sync --extra dev

install-docs:
	uv sync --extra docs

install-gui:
	uv sync --extra gui --active

lint:
	uv run ruff check .

typecheck:
	uv run pyright || true

test:
	uv run pytest -vv

cov:
	uv run pytest --cov=oops --cov-branch --cov-report=term-missing

cov-html:
	uv run pytest --cov=oops --cov-branch --cov-report=html
	@echo "Open htmlcov/index.html"

build:
	uv build

build-ui:
	cd ui && npm ci && npm run build

docs:
	uv run mkdocs build

docs-serve: install-docs
	uv run mkdocs serve --watch src/oops/

clean:
	rm -rf build dist site *.egg-info .pytest_cache .ruff_cache .mypy_cache .pyright
