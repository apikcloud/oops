# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-04-05

### Documentation

- Add versioned documentation with `mike` (version switcher, `latest` alias)
- Switch installation guide to `uv sync` and pin doc links to `v0.2.0`
- Add venv activation step to contributing guide

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
