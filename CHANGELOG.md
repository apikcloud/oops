# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
