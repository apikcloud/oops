# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**oops** is a Python CLI toolkit for managing complex Odoo multi-repository projects. It automates Git submodule management, generates addon inventories, normalizes Odoo manifest files, and integrates with CI pipelines. It is Apik-specific by design (hardcoded defaults for author, maintainers, paths, etc.) but structured to be forkable.

## Commands

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"
# or
make install   # adds --break-system-packages

# Lint
make lint      # ruff check
make typecheck # pyright (soft-fail — informational only)

# Test
make test      # pytest -vv
make cov       # pytest with coverage (80% minimum enforced)
pytest -vv tests/path/to/test_file.py::TestClass::test_name  # single test

# Build
make build
```

## Architecture

```
oops/
├── commands/       # 18 Click CLI entry points, grouped by domain
│   ├── addons/     # list, add, download, materialize, diff, table
│   ├── manifest/   # check, fix/rewrite
│   ├── project/    # check, info, update, exclude
│   └── submodules/ # add, update, check, fix, prune, rename, replace, rewrite, show, flatten, branch, clean
├── core/
│   ├── config.py   # Global Config dataclass — Apik defaults (paths, manifest fields, Docker images)
│   ├── models.py   # AddonInfo, CommitInfo, ImageInfo, WorkflowRunInfo
│   ├── exceptions.py
│   └── messages.py # Commit message templates
├── git/
│   ├── core.py     # GitRepository class — central git abstraction (commits, staging, submodules)
│   ├── submodules.py
│   ├── versioning.py
│   └── ...
├── rules/          # Fixit-based lint rules for Odoo manifests
├── services/       # Docker and GitHub API integrations
└── utils/
    ├── io.py       # Addon discovery, manifest parsing (ast.literal_eval), symlink ops
    ├── render.py   # Rich-based terminal output (tables, colors)
    ├── net.py      # URL normalization
    └── tools.py    # Subprocess wrappers
```

### Key Design Points

- **Entry points** are declared in `pyproject.toml` under `[project.scripts]`. Each command maps to a Click function in `oops/commands/`.
- **`GitRepository`** (`git/core.py`) is the main interface for all git operations — most commands instantiate it first.
- **`Config`** (`core/config.py`) holds global defaults; submodule third-party addons live in `.third-party/` (new) or `third-party/` (old).
- **Manifest parsing** uses `ast.literal_eval` (not `importlib`). Manifest normalization/rewriting uses `libcst` to preserve comments.
- **Fixit rules** in `rules/` enforce manifest authorship (`author = "Apik"`) and a fixed allowed-maintainers list.
- **Version** is derived from git tags via `hatch-vcs` — no manual version bumping.

### Key Libraries

| Library | Role |
|---------|------|
| Click | CLI framework |
| GitPython | Git repo operations |
| libcst | AST-preserving manifest rewriting |
| fixit | Custom lint rules |
| Rich | Terminal output |
| Ruff | Linting + formatting (line-length=100, py37 target) |
| Pyright | Type checking (basic mode) |
