# Makefile for oops project
# Requires Python >=3.7 and uv. Install all dev tools: make install

SHELL := bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

# --- Project ---
PROJECT  ?= oops
SRC_DIR  ?= src

# --- Git ---
VERSION    ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
COMMIT     ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# ============================================================================
.DEFAULT_GOAL := help

##@ Setup

.PHONY: install
install: ## Install package in editable mode (dev + gui + mcp extras)
	uv sync --extra dev --extra gui --extra mcp --extra migrate --active

.PHONY: install-docs
install-docs: ## Install docs dependencies
	uv sync --extra docs

.PHONY: install-gui
install-gui: ## Install GUI (pywebview) dependencies
	uv sync --extra gui --active

##@ Development

.PHONY: run
run: ## Run the oops CLI entry point
	uv run oops

##@ Testing

.PHONY: test
test: ## Run pytest suite
	uv run pytest -vv

.PHONY: cov
cov: ## Run pytest with branch coverage (terminal report)
	uv run pytest --cov=oops --cov-branch --cov-report=term-missing

.PHONY: cov-html
cov-html: ## Run pytest with branch coverage (HTML report → htmlcov/)
	uv run pytest --cov=oops --cov-branch --cov-report=html
	@echo "Open htmlcov/index.html"

##@ Code Quality

.PHONY: lint
lint: ## Run ruff linter
	uv run ruff check .

.PHONY: lint-fix
lint-fix: ## Run ruff linter with auto-fix
	uv run ruff check --fix .

.PHONY: fmt
fmt: ## Format code with ruff
	uv run ruff format .

.PHONY: fmt-check
fmt-check: ## Check code formatting (no changes)
	uv run ruff format --check .

.PHONY: typecheck
typecheck: ## Run pyright type checking (soft-fail — informational only)
	uv run pyright || true

##@ CI

.PHONY: ci
ci: lint fmt-check typecheck test ## Run full CI pipeline (lint + fmt-check + typecheck + test)

##@ Build

.PHONY: build
build: ## Build wheel and sdist
	uv build

.PHONY: build-ui
build-ui: ## Build UI bundle (requires Node.js)
	cd ui && npm ci && npm run build

##@ Documentation

.PHONY: docs
docs: ## Build MkDocs documentation site
	uv run mkdocs build

.PHONY: docs-serve
docs-serve: install-docs ## Reinstall docs deps and serve with live-reload
	uv run mkdocs serve --watch src/oops/

##@ Cleanup

.PHONY: clean
clean: ## Remove build artifacts and caches
	rm -rf build dist site *.egg-info .pytest_cache .ruff_cache .mypy_cache .pyright htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

##@ Help

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2} \
		/^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)}' $(MAKEFILE_LIST)
