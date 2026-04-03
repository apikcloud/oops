# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**oops** is a Python CLI toolkit for managing complex Odoo multi-repository projects. It automates Git submodule management, generates addon inventories, normalizes Odoo manifest files, and integrates with CI pipelines. It is Apik-specific by design (hardcoded defaults for author, maintainers, paths, etc.) but structured to be forkable.

## Commands

```bash
# Install in editable mode with dev dependencies
uv sync --extra dev
# or
make install

# Lint
make lint      # ruff check
make typecheck # pyright (soft-fail — informational only)

# Test
make test      # pytest -vv
make cov       # pytest with coverage (80% minimum enforced)
uv run pytest -vv tests/path/to/test_file.py::TestClass::test_name  # single test

# Docs
make install-docs  # install docs dependencies
make docs          # build static site
make docs-serve    # live-reload dev server

# Build
make build
```

## Architecture

```
oops/
├── commands/       # Click CLI entry points, grouped by domain
│   ├── addons/     # list, add, compare, download, materialize, diff
│   ├── manifest/   # check, fix (entry points declared but not yet implemented)
│   ├── project/    # check, info, update, exclude
│   ├── readme/     # update (generate addon table in README.md)
│   └── submodules/ # add, update, check, fix, prune, rename, replace, rewrite, show, branch, clean
├── core/
│   ├── config.py   # Nested Config dataclasses + YAML loader (see below)
│   ├── models.py   # AddonInfo, CommitInfo, ImageInfo, WorkflowRunInfo
│   ├── exceptions.py
│   └── messages.py # All git commit message strings
├── git/
│   ├── core.py        # GitRepository class — legacy abstraction (commits, staging, submodules)
│   ├── repository.py  # Standalone helpers: get_last_commit, update_gitignore, list_available_addons
│   ├── submodules.py
│   ├── versioning.py
│   └── __init__.py    # Re-exports from submodules — marked deprecated, will be removed
├── rules/          # Fixit-based lint rules for Odoo manifests
├── services/       # Docker and GitHub API integrations
└── utils/
    ├── io.py       # Addon discovery, manifest parsing (ast.literal_eval), symlink ops
    ├── render.py   # Terminal output (tables, colors)
    ├── net.py      # URL normalization
    └── tools.py    # Subprocess wrappers
```

### Config structure (`core/config.py`)

`Config` is a nested dataclass loaded from `~/.oops.yaml` (global) and `.oops.yaml` (local, takes precedence). Unknown keys are silently ignored.

```
Config
├── images: ImagesConfig
│   ├── source: ImageSourceConfig      # repository, file, .url property
│   ├── collections: list[str]
│   ├── registries: ImageRegistriesConfig  # recommended, deprecated, warn
│   └── release_warn_age_days: int
├── submodules: SubmodulesConfig
│   ├── current_path: Path             # .third-party
│   ├── old_paths: list[Path]          # [third-party]
│   ├── force_scheme: str              # ssh
│   ├── deprecated_repositories: dict
│   └── checks: list[str]
└── project: ProjectConfig
    ├── mandatory_files / recommended_files
    ├── file_packages / file_requirements / file_odoo_version
    └── migrate_command / migrate_content
```

Access pattern: `config.images.registries.recommended`, `config.submodules.current_path`, etc.

### Key Design Points

- **Entry points** are declared in `pyproject.toml` under `[project.scripts]`. Each command maps to a Click function in `oops/commands/`. `oops-man-check` and `oops-man-fix` are declared but their implementation files don't exist yet.
- **Two git abstraction layers coexist**: newer commands use GitPython's `Repo` directly; older ones use the custom `GitRepository` class (`git/core.py`). Both are acceptable — don't unify unless refactoring a whole domain.
- **`oops.git` and `oops.git.config`** are marked deprecated (`# TODO: deprecated`). Import directly from `oops.git.repository`, `oops.git.versioning`, etc. instead.
- **Manifest parsing** uses `ast.literal_eval` (not `importlib`). Manifest normalization/rewriting uses `libcst` to preserve comments.
- **Fixit rules** in `rules/` enforce manifest authorship (`author = "Apik"`) and a fixed allowed-maintainers list.
- **Version** is derived from git tags via `hatch-vcs` — no manual version bumping.
- **Docs** live in `docs/` and are built with MkDocs + mkdocs-material. Command reference pages under `docs/commands/` are the canonical user-facing docs.

### Key Libraries

| Library | Role |
|---------|------|
| Click | CLI framework |
| GitPython | Git repo operations |
| libcst | AST-preserving manifest rewriting |
| fixit | Custom lint rules |
| Rich / tabulate | Terminal output |
| Ruff | Linting + formatting (line-length=100, py37 target) |
| Pyright | Type checking (basic mode) |
| MkDocs + mkdocs-material | Documentation site |
