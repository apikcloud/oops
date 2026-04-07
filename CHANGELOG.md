# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
