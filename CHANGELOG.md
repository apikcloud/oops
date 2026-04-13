# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-04-13

### Added

- `oops --version`: display the installed package version
- `oops-sub-remove`: remove a submodule via an indexed interactive menu
- `oops-misc-new-project`: create a new GitHub repository from a template, clone locally, and trigger the update workflow
- `oops-misc-edit-config`: open the global or local `.oops.yaml` in the default editor
- `oops-pro-exclude`: `--hook` flag raises an error when the exclusion list was updated, prompting pre-commit to re-run
- `oops-man-check`: accepts addon names, manifest file paths, or addon directories — unified CLI and pre-commit entry point; `--names` option and separate `oops-man-precommit` entry point removed

### Changed

- `oops-pro-check`: output now uses `print_warning` / `print_error` / `print_success` helpers instead of a table

### Fixed

- `oops-sub-check`: fixed false positive on PR submodule placement check

### Documentation

- Hooks page updated with remote repo config and corrected `pass_filenames` examples
- Command reference: fixed stale `--names` example for `oops-man-check` and added `--hook` example for `oops-pro-exclude`

## [0.7.0] - 2026-04-10

### Added

- `oops-pro-init`: scaffold a Docker Compose stack and `odoo.conf` for a new project; supports optional maildev and SFTP services (`--with-maildev`, `--with-sftp`), port override (`--port`), and dev-mode toggle (`--no-dev`)
- `oops-pro-sync`: `--branch`/`-b` and `--files`/`-F` CLI overrides to target a specific remote branch or a custom file list at runtime

### Changed

- `io/file.py`: `file_updater` now accepts and propagates a `dry_run` parameter; callers no longer need manual if/else branching
- `io/file.py`: extracted `get_excluded_addon_names` and `get_filtered_addon_names` helpers (with docstrings and unit tests) from `exclude.py`

### Fixed

- `oops-pro-exclude`: content formatting crashed when the addon list was non-iterable (e.g. a generator); added explicit list conversion
- `oops-pro-exclude`: overhauled installable filtering, per-line `addon/|` format, and ensured changes are always committed
- `oops-pro-show`: packages and requirements rows removed from the display (they duplicated data shown elsewhere)
- CLI commands: switched to the shared `@command` decorator for consistent repo resolution and error handling

## [0.6.2] - 2026-04-10

### Documentation

- Command pages: each group now shows its module docstring as an intro blurb (via mkdocstrings)
- Command entries sorted alphabetically within all command pages

## [0.6.1] - 2026-04-10

### Changed

- Package source tree moved to `src/` layout

### Fixed

- Coverage `omit` pattern for `oops/commands/*` no longer matched after the `src/` move — restored with a wildcard prefix
- `file_updater` docstring: `append_position` description was a run-on sentence; rewritten with clear per-value explanations

### Documentation

- `docs/commands/misc.md`: corrected module path for `oops-misc-create-workspace` and added missing `oops-misc-view-doc` entry

## [0.6.0] - 2026-04-09

### Added

- `oops-sub-init`: initialize and update all submodules recursively with configurable parallel jobs (`-j/--jobs`, default: 4)
- `oops-pro-exclude`: generate the pre-commit exclusion list for third-party addons
- `oops-req-check`: compare `requirements.txt` against addon manifest dependencies and exit non-zero on differences
- `oops-req-update`: update `requirements.txt` from addon manifest `external_dependencies`
- `oops-readme-update`: generate the addon table in README.md with version, maintainer avatars, and summary

### Fixed

- `oops-sub-fix`, `oops-sub-check`: URL scheme detection always triggered because `parse_repository_url` returns a canonical URL string, not the scheme — switched to `_parse_url`
- `oops-sub-fix`: removed dead deprecated-repo replacement code; added `--dry-run`; replaced `click.Abort()` with `UsageError`; added completion messages
- `oops-pro-exclude`: hardcoded `.pre-commit-config.yaml` path ignored the configured value
- `oops-readme-update`: `--no-commit` flag default was inverted, preventing commits in all cases

## [0.5.0] - 2026-04-08

### Added

- `oops-misc-view-doc`: open the oops documentation site in the default browser
- `oops-misc-create-workspace`: generate a VSCode workspace file for the current Odoo project
- CLI auto-discovers command groups at startup from the package structure
- CLI group descriptions sourced from `__init__.py` module docstrings
- `addons materialize`: redesigned to include all addons by default, with `--include`/`--exclude` filters

### Changed

- `parse_odoo_version` now returns an `ImageInfo` object
- `normalize_version` moved to `utils/helpers`

### Fixed

- `remove_and_add` now uses `repo.git.add()` to correctly stage directories

## [0.4.0] - 2026-04-07

### Added

- `oops-odoo-download`: clone Odoo Community and Enterprise source repositories via SSH into a shared team directory configured in `~/.oops.yaml`
- `oops-odoo-update`: update an existing checkout to the latest commit, or snapshot it at a given date (`--date YYYY-MM-DD`)
- `oops-odoo-show`: list all local Odoo source checkouts with their current commit hash and date, grouped by version
- `ManifestVersionBump` lint rule: enforces version bump on modified manifests; supports `strict` and `trunk` strategies (configurable via `manifest.version_bump_strategy`)
- `OdooConfig` section in `~/.oops.yaml`: `sources_dir`, `community_url`, `enterprise_url`

### Fixed

- Config `_apply()` now correctly converts `Optional[Path]` fields (previously failed when the default was `None`); also expands `~` in path values

### Documentation

- Added command reference page for the new `odoo` command group
- Added manifest configuration section, lint rules page, and pre-commit hooks guide

## [0.3.1] - 2026-04-07

### Fixed

- Eliminate spurious `UserWarning: Unknown config key ignored: 'version'` by adding `version` as an accepted field in the root `Config` dataclass

## [0.3.0] - 2026-04-06

### Added

- `manifest check` and `manifest fix` commands backed by configurable fixit lint rules: required keys, author/maintainers/summary validation (with autofix), version format enforced per `odoo_version` config (digit-typo autofix O→0/l→1), canonical key ordering
- `release create` and `release show` commands for semver release management
- `project sync` command: sparse-clones a remote repository and copies configured files into the local project tree
- Lazy Config singleton: configuration is loaded on first access; a clear error is raised immediately when no `.oops.yaml` is found instead of crashing later
- `sub check` now warns when submodules point to a PR branch (detected via `pull_request_dir` config)
- `find_addon_dirs()` helper in `io/file.py`; `pull_request_dir` field in `ProjectConfig`
- Shared CST helpers in `rules/_helpers.py` for reuse across future lint rule modules
- YAML config support for `~/.oops.yaml` and `.oops.yaml` with `version` key validation

### Changed

- All commands unified under a shared `OopsCommand` base class with consistent repo resolution and error handling
- Removed legacy `oops/git/` module; all git operations consolidated into `services/git.py`
- File I/O reorganized into `oops/io/` (`file.py`, `manifest.py`, `tools.py`)

## [0.2.0] - 2026-04-03

### Added

- `addons compare` command to compare addons between two sources
- `sub replace` command for in-place submodule replacement
- `sub fix` command for submodule repair

### Changed

- Migrated internals to GitPython library
- Reorganized module structure; decoupled git operations from commands

### Fixed

- Fixed `addons diff` command to correctly find modified addons
- Fixed logic errors and improved error handling across commands
- Fixed entry points and imports after module restructuring
- Fixed `sub add` error path handling
- Made addon migrate script executable

## [v0.1.0] - 2025-11-19

### Added

- First release version with initial features for addons, projects, and submodules.
