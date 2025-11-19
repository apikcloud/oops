# oops - Odoo Scripts & Helpers

oops bundles a set of opinionated command-line utilities used at Apik to keep complex Odoo
multi-repository projects in check. It streamlines Git submodule management, generates addon
inventories, and normalizes Odoo manifests so teams can focus on delivering features instead of
chasing repository drift.

## Why use oops?
- Automates adding, auditing, and pruning Git submodules across multiple Odoo repositories.
- Builds addon lists and tables directly from manifests for documentation or reporting.
- Normalizes `__manifest__.py` files while preserving comments and project-specific tweaks.
- Ships reproducible scripts that integrate well with CI pipelines and project bootstrap tooling.

## Requirements
- Python 3.8+ (Python 3.7 is the minimum supported version).
- Git with submodule support enabled.
- A POSIX-compatible shell; examples below assume `bash`.

## Installation

### From GitHub (recommended)
```bash
pip install git+https://github.com/apikcloud/oops.git
```

### Local development checkout
```bash
git clone https://github.com/apikcloud/oops.git
cd oops
pip install -e .
```

## Quick start
```bash
# Add an OCA submodule and create symlinks for each addon it contains
oops-sub-add https://github.com/OCA/server-ux.git -b 18.0 --auto-symlinks

# List every addon discovered in the configured submodules
oops-addons-list --format json > addons.json

# Reformat every __manifest__.py under ./addons and exit non-zero on pending changes
oops-man-rewrite --addons-dir ./addons --check
```

You can also access the same commands through the unified CLI:
```bash
oops sub add https://github.com/OCA/server-ux.git -b 18.0 --auto-symlinks
oops addons list --format table
oops manifest rewrite --addons-dir ./addons --check
```

## CLI overview
The package exposes several entry points (available as standalone executables or via
`oops <group> <command>`):

### Submodule management (`oops sub ...`)
- `oops-sub-add URL -b BRANCH [options]`: clones an Odoo addon repository into `.third-party/<ORG>/<REPO>`,
  optionally wiring symlinks to the addons it ships. Useful flags include `--auto-symlinks`,
  `--addons` to restrict the selection, `--dry-run`, and `--no-commit`.
- `oops-sub-check`: ensures every submodule lives under `.third-party/` and that at least one symlink points
  to it.
- `oops-sub-rewrite`: realigns submodule paths with their canonical origin, updates `.gitmodules`, moves
  directories, and refreshes symlinks. Combine with `--dry-run`, `--yes`, or `--no-commit` depending on
  your review process.
- `oops-sub-prune`: detects submodules that are no longer referenced by symlinks and guides you through a
  clean removal, including `git submodule deinit` and cache cleanup.
- `oops-sub-clean [--reset]`: removes empty `.third-party` directories, optionally performs a
  `git reset --hard`, and re-initializes submodules.
- `oops-sub-flatten [PATH]`: replaces symlinks under `PATH` with the actual addon sources, which is handy
  when shipping tarballs without symlinks.

### Addon inventory (`oops addons ...`)
- `oops-addons-list`: scans configured submodules and prints addon metadata in `text`, `json`, or `csv`
  format. Use `--only NAME` to filter, or `--init-missing` to bootstrap missing manifests.
- `oops-addons-table`: replaces `[//]: # (addons)` markers inside Markdown documents with a generated table
  driven by manifests. Options include `--addons-dir`, `--readme-path`, and commit toggles.
- `oops-addons-add` and `oops-addons-download`: utility commands to pull addon archives and populate local
  directories.

### Manifest normalization (`oops manifest ...`)
- `oops-man-rewrite`: applies LibCST-powered transformations to fix typos, enforce maintainers, order
  dependencies, and add missing headers. Supports `--dry` for read-only runs and `--check` for CI.
- `oops-man-check`: lightweight manifest validation that reports style or content issues.
- `oops-man-fix`: legacy formatter kept for ad-hoc adjustments when experimenting.

### Project helpers (`oops project ...`)
- `oops-pro-check`: runs consistency checks across the current project tree, surfacing missing
  configuration or drift that would make CI fail.

Refer to the individual command help (`--help`) for full option lists.

## Typical workflows and best practices
- Add `oops-man-rewrite --check` to your CI to guarantee consistent manifests before merging.
- Combine `oops-addons-list` with tools like `jq` or `csvkit` to audit addon inventories pulled via
  submodules.
- Run `oops-sub-rewrite --dry-run` prior to reorganizing submodules so you can share the migration plan
  with teammates.
- Use `oops-sub-flatten` when preparing deliverables for environments that cannot handle symlinks.

## Development
1. Create and activate a virtual environment.
2. Install development dependencies: `pip install -e .[dev]` (or `make install`).
3. Run quality checks before opening a pull request:
   - `make lint` to execute Ruff.
   - `make typecheck` to run Pyright (soft-fail by design).
   - `make test` to execute the pytest suite.
4. Build artifacts locally with `make build` when you need wheels or source distributions.

## Contributing and support
Issues and pull requests are welcome on GitHub. Please include clear reproduction steps, add tests or
changelog fragments when relevant, and describe the impact on downstream projects so reviews can move
quickly. The scripts are provided as-is by the Apik team; feel free to fork if you need bespoke behavior.

## License
oops is distributed under the AGPL-3.0-only license. See `LICENSE` or visit
https://www.gnu.org/licenses/agpl-3.0.html for the full text.
