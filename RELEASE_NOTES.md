# Release Notes

This page summarises what's new, improved, or fixed in each version of `oops`.

---

## [0.12.3] - 2026-04-27

A small fix for the addons workflow.

### 🐛 Fixes

- `oops addons`: fixed an issue where the migration command was printed even when no file was saved

---

## [0.12.2] - 2026-04-27

A small fix in the release tooling.

### 🐛 Fixes

- Fixed an issue where generated changelog section headers were missing the `v` prefix in version numbers

---

## [0.12.1] - 2026-04-23

A targeted bug fix for the `oops submodules add` command.

### 🐛 Fixes

- `oops submodules add`: fixed an issue where incorrect file paths were staged after adding a new submodule

---

## [0.12.0] - 2026-04-16

Small quality-of-life improvements and a bug fix in the project initialisation.

### ✨ What's new

- **`oops requirements check --no-fail`**: you can now run the requirements check without blocking your workflow — differences are still displayed, but the command exits successfully

### 🔄 Changes

- **`oops project exclude`**: the pre-commit flag has been renamed from `--hook` to `--fail` for consistency with other commands

### 🐛 Fixes

- `oops project init`: the generated `docker-compose.yml` now correctly mounts `./.config` instead of `./config` for the Odoo configuration directory

---

## [0.11.0] - 2026-04-16

Improved workspace generation and a more ergonomic submodule workflow.

### ✨ What's new

- **Odoo sources in your workspace**: `oops misc create-workspace` and `oops project init` now accept `--include-sources` to add the Odoo Community and Enterprise source directories as workspace folders in VSCode — great for go-to-definition and cross-project navigation

### 🔄 Changes

- **`oops submodules add` reworked**: the branch is now the first argument (before the URL), a `-y/--yes` flag skips the confirmation prompt, the URL scheme is automatically normalized to the configured value, and a pre-flight check prevents confusing errors when a stale `.git/modules` directory already exists

### 🐛 Fixes

- `oops odoo show`: the `--base-dir` option has been removed — the sources directory is now always read from `odoo.sources_dir` in config, consistent with all other Odoo commands

---

## [0.10.0] - 2026-04-14

Usage tracking and a new pre-commit hook for Python requirements validation.

### ✨ What's new

- **Usage statistics**: every `oops` command invocation is recorded locally; run `oops misc usage` to see which commands you use most, sorted by frequency
- **Requirements pre-commit hook**: a new `check-requirements` hook validates that `requirements.txt` is in sync with addon manifest dependencies — catches missing or extra entries before they reach CI

---

## [0.9.0] - 2026-04-14

Smarter workspace generation: missing Odoo sources are fetched automatically.

### ✨ What's new

- `oops misc create-workspace` now downloads missing Odoo sources automatically before generating the workspace file; use `--without-download` to opt out

### 🔄 Changes

- Workspace Python analysis paths now reflect the actual project edition (community-only vs community + enterprise)
- `oops addons download` switches to SSH `git clone` (depth=1) — no GitHub token required; `.gitignore` entries are managed with tagged blocks that accumulate across runs

### 🐛 Fixes

- `oops addons download`: fixed a silent `.gitignore` corruption that wrote a comma-joined string instead of one entry per line

---

## [0.8.0] - 2026-04-13

New commands for project creation, config editing, and submodule removal.

### ✨ What's new

- **`oops --version`**: display the installed version at any time
- **Remove a submodule interactively**: `oops submodules remove` presents a numbered menu to pick the submodule to delete
- **Create a new GitHub project**: `oops misc new-project` scaffolds a repository from a template, clones it locally, and triggers the update workflow — all in one command
- **Edit your config**: `oops misc edit-config` opens `~/.oops.yaml` (or the local `.oops.yaml`) directly in your default editor
- **Pre-commit hook integration**: `oops project exclude --hook` raises an error when the exclusion list was updated, prompting pre-commit to re-run automatically
- **Unified manifest checker**: `oops-check-manifest` now accepts addon names, file paths, or directories — works identically from the CLI and from pre-commit

### 🐛 Fixes

- `oops submodules check`: fixed a false positive on pull-request submodule placement

---

## [0.7.0] - 2026-04-10

New command to scaffold a complete Docker Compose stack for an Odoo project.

### ✨ What's new

- **`oops project init`**: generates `docker-compose.yml` and `.config/odoo.conf` for the current project; optional services (`--with-maildev`, `--with-sftp`), port override (`--port`), and production-like mode (`--no-dev`)
- **`oops project sync` overrides**: `--branch` and `--files` let you target a specific remote branch or file list at call time, without touching the config

### 🐛 Fixes

- `oops project exclude`: fixed a crash when the addon list was a generator; overhauled formatting and ensured changes are always committed
- `oops project show`: removed duplicate package and requirements rows from the output

---

## [0.6.0] - 2026-04-09

Batch submodule initialization, README generation, and requirements management.

### ✨ What's new

- **`oops submodules init`**: initialize and update all submodules recursively with configurable parallel jobs (`-j/--jobs`, default 4)
- **`oops project exclude`**: generate the pre-commit exclusion list for third-party addons automatically
- **Requirements management**: `oops requirements check` compares `requirements.txt` against manifest dependencies; `oops requirements update` rewrites it from scratch
- **`oops readme update`**: generate the addon table in `README.md` with version badges, maintainer avatars, and summaries

### 🐛 Fixes

- `oops submodules fix` and `oops submodules check`: fixed URL scheme detection that always triggered due to incorrect scheme comparison
- `oops readme update`: `--no-commit` flag default was inverted, preventing commits in all cases

---

## [0.5.0] - 2026-04-08

Documentation browser, VSCode workspace generator, and auto-discovery of command groups.

### ✨ What's new

- **`oops misc view-doc`**: open the `oops` documentation site in your default browser
- **`oops misc create-workspace`**: generate a ready-to-use VSCode workspace file for any Odoo project
- Command groups are now auto-discovered at startup — adding a new group requires no manual registration
- `oops addons materialize`: redesigned with `--include`/`--exclude` filters; materializes all addons by default

---

## [0.4.0] - 2026-04-07

Full Odoo source management and a manifest version-bump lint rule.

### ✨ What's new

- **Odoo source commands**: `oops odoo download` clones Community and Enterprise via SSH into a shared team directory; `oops odoo update` pulls the latest commit or snapshots at a given date (`--date`); `oops odoo show` lists all local checkouts with their commit hash and date
- **Manifest version bump rule**: `ManifestVersionBump` enforces that the version is bumped on modified manifests; supports `strict` (every commit) and `trunk` (once per release) strategies
- New `odoo` section in `~/.oops.yaml`: configure `sources_dir`, `community_url`, and `enterprise_url`

### 🐛 Fixes

- Config loading: `~` is now correctly expanded in path values; `Optional[Path]` fields no longer crash when the default is `None`

---

## [0.3.1] - 2026-04-07

### 🐛 Fixes

- Eliminated a spurious `UserWarning: Unknown config key ignored: 'version'` on every config load

---

## [0.3.0] - 2026-04-06

Manifest linting, release management, and project file sync.

### ✨ What's new

- **Manifest lint and autofix**: `oops manifest check` and `oops manifest fix` enforce required keys, author/maintainers/summary rules, version format, and canonical key ordering — all configurable via `.oops.yaml`
- **Release commands**: `oops release create` and `oops release show` for semver release management
- **`oops project sync`**: sparse-clone a remote repository and copy configured files (CI workflows, pre-commit config, etc.) into the local project
- Config is now loaded lazily on first access — a clear error is shown immediately when no `.oops.yaml` is found

### 🔄 Changes

- All commands unified under a shared base class for consistent repo resolution and error handling
- Legacy `oops/git/` module removed; all git operations consolidated into `services/git.py`

---

## [0.2.0] - 2026-04-03

New submodule and addon commands, migration to GitPython.

### ✨ What's new

- `oops addons compare`: compare addon lists between two sources
- `oops submodules replace`: replace a submodule in-place
- `oops submodules fix`: repair broken submodule configuration

### 🔄 Changes

- Migrated internals to the GitPython library for more reliable git operations
- Module structure reorganized; git operations decoupled from command logic

### 🐛 Fixes

- `oops addons diff`: fixed detection of modified addons
- `oops submodules add`: fixed error path handling
- Fixed entry points and imports after module restructuring

---

## [0.1.0] - 2025-11-19

First public release of `oops` with initial support for addon management, project configuration, and git submodule workflows.
