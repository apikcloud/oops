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
│   ├── manifest/   # check, fix — entry points declared, implementations MISSING
│   ├── project/    # check, show, update, exclusions, sync
│   ├── readme/     # update (generate addon table in README.md)
│   ├── release/    # create, show
│   └── submodules/ # add, update, check, fix, prune, rename, replace, rewrite, show, branch, clean
├── core/
│   ├── config.py   # Nested Config dataclasses + YAML loader (see below)
│   ├── paths.py    # Structural path constants (repo layout)
│   ├── models.py   # AddonInfo, CommitInfo, ImageInfo, WorkflowRunInfo
│   ├── exceptions.py
│   └── messages.py # All git commit message strings (keyed by name, used by commit())
├── io/
│   ├── file.py     # File I/O helpers, addon discovery, migration script generation
│   ├── manifest.py # Manifest parsing (ast.literal_eval) and libcst-based rewriting
│   └── tools.py    # Subprocess wrappers (run())
├── rules/          # Fixit-based lint rules for Odoo manifests
├── services/
│   ├── git.py      # GitPython helpers: get_local_repo(), commit(), list_available_addons(), get_last_commit()
│   ├── github.py   # GitHub API integration
│   └── docker.py   # Docker image discovery and validation
└── utils/
    ├── helpers.py  # String utilities, deep_visit
    ├── render.py   # Terminal output (tables, colors, print_success/warning/error)
    ├── net.py      # URL normalization, sparse_clone
    └── versioning.py # Semver helpers (get_last_release, get_next_releases, is_valid_semver)
```

### Config structure (`core/config.py`)

`Config` is a nested dataclass loaded from `~/.oops.yaml` (global) and `.oops.yaml` (local, takes precedence). Unknown keys emit a warning but are not rejected.

```
Config
├── images: ImagesConfig
│   ├── source: ImageSourceConfig      # repository (required), file (required), .url property
│   ├── collections: list[str]
│   ├── registries: ImageRegistriesConfig  # recommended, deprecated, warn
│   └── release_warn_age_days: int
├── submodules: SubmodulesConfig
│   ├── current_path: Path             # .third-party
│   ├── old_paths: list[Path]          # [third-party]
│   ├── force_scheme: str              # ssh
│   ├── deprecated_repositories: dict
│   └── checks: list[str]
├── project: ProjectConfig
│   ├── mandatory_files / recommended_files
│   ├── file_packages / file_requirements / file_odoo_version / file_migrate
│   └── pre_commit_exclude_file
└── sync: SyncConfig
    ├── remote_url / branch
    └── files: list[str]
```

Access pattern: `config.images.registries.recommended`, `config.submodules.current_path`, etc.

### Key Design Points

- **Entry points** are declared in `pyproject.toml` under `[project.scripts]`. `oops-man-check` and `oops-man-fix` are declared but have no implementation — their command files are missing. `oops-i-did-it-again` is an alias for `oops-sub-clean`.
- **Single git abstraction layer**: all commands use GitPython's `Repo` directly plus helpers from `services/git.py`. The legacy `GitRepository` class and the entire `oops/git/` module have been removed — do not re-introduce them.
- **`services/git.py`** is the canonical git service layer: `get_local_repo()` resolves the repo, `commit()` stages and commits using a named key from `core/messages.py`, `list_available_addons()` iterates submodules, `list_submodules(repo)` returns a `rel_path → metadata` dict (cached via `_list_submodules_cached(working_dir)` — `Repo` is not hashable so the cache key is the string working dir).
- **Commit messages** are all stored as format strings in `core/messages.py` (`CommitMessages` dataclass). Always add new messages there and reference them by key in `commit()` calls.
- **Manifest parsing** uses `ast.literal_eval` (not `importlib`). Manifest normalization/rewriting uses `libcst` to preserve comments and formatting.
- **Error-exit conventions**: command callbacks must surface failures through Click, never via bare `sys.exit()` / `raise SystemExit` / `ctx.exit()`:
  - Clean intentional exit from any depth: `raise EarlyExit()` (exit 0).
  - Fatal business error: `raise OopsError(msg)` from `oops.core.exceptions` — renders as `✘ msg` in red on stderr, exits 1.
  - Specialised business errors (subclasses of `OopsError`): `ConfigError(msg)` (exit 1), `APIError(msg)` (exit 2), `NotFoundError(msg)` (exit 3).
  - Bad option / mutually exclusive flags: `raise click.UsageError(msg)` (exit 2).
  - User declined confirmation: `raise AppAbort()` (exit 1, prints "Aborted!").
  - Any unhandled Python exception is auto-wrapped into `OopsError(f"Unexpected error: {exc}")` by `OopsCommand.invoke()`.
  - The regression test `tests/test_core_and_utils.py::test_termination_patterns_in_commands` enforces this in CI.
- **Fixit rules** in `rules/` enforce manifest authorship (`author = "Apik"`) and a fixed allowed-maintainers list.
- **Version** is derived from git tags via `hatch-vcs` — no manual version bumping.
- **Docs** live in `docs/` and are built with MkDocs + mkdocs-material. Versioned with `mike`. Command reference pages under `docs/commands/` are the canonical user-facing docs; API reference pages under `docs/reference/` are auto-generated from docstrings.

### AddonInfo model and addon enrichment

`AddonInfo` (`core/models.py`) has two field groups:

- **Manifest + filesystem fields** — always populated by `from_path()`. Keep `from_path()` pure: no git calls, no submodule lookups.
- **Git-state fields** (`submodule`, `branch`, `pull_request`, `classification`) — `Optional`, default `None`. `None` means "not yet enriched"; `""` means "enriched, not in a submodule". These are populated by calling `enrich_addon(addon, sub)` from `io/file.py`.

**`enrich_addon(addon, sub)`** takes the addon and the pre-fetched submodule metadata dict for its `rel_path` (from `list_submodules`). It fills git-state fields and computes `classification` in one call. Classification priority (first match wins):
1. Author contains `"(OCA)"` → `"oca"`
2. Author matches `config.manifest.author` → `"custom"`
3. Technical name starts with `config.project.prefix` → `"custom"`
4. Submodule org is `"OCA"` or matches `config.github.owner` → `"oca"` / `"custom"`
5. Fallback → `"third-party"`

Classification values are always lowercase: `"custom"` | `"oca"` | `"third-party"`.

**`addon.location`** is a derived property (no enrichment needed): `"active"` (symlinked to root — Odoo-visible), `"local"` (at root, not a symlink — project-owned), `"inactive"` (in submodule tree, not symlinked — present but Odoo can't see it).

**`oops addons list --all`** deduplication: `os.walk(followlinks=True)` visits both the root symlink and its resolved target. The `seen` dict in `list.py` prefers `addon.symlinked` entries on collision — without this, dotfile dirs (`.third-party`) sorting first causes symlinks to be miscounted as inactive addons.

### Known Limitations

- Symlink detection assumes **one symlink per submodule** — commands that discover symlinks (rewrite, io/file.py) have a `FIXME` noting this.
- `oops-man-check` and `oops-man-fix` are non-functional (declared but not implemented).
- `oops-addons-download` does not check for duplicate addons before copying (`FIXME` in download.py).

### Key Libraries

| Library | Role |
|---------|------|
| Click | CLI framework |
| GitPython | Git repo operations |
| libcst | AST-preserving manifest rewriting |
| fixit | Custom lint rules (py≥3.9 only) |
| tabulate | Terminal tables |
| Ruff | Linting + formatting (line-length=100, py37 target) |
| Pyright | Type checking (basic mode, soft-fail) |
| MkDocs + mkdocs-material + mike | Documentation site with versioning |
