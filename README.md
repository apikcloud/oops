# Oops

Oops bundles a set of opinionated command-line utilities used at Apik to keep complex Odoo
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
