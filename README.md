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
- Python 3.7+.
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

# Generate or refresh the addons table in README.md
oops-readme-update
```

## Commands

### Submodule commands

#### `oops-sub-add <url>`
Add a git submodule and optionally create symlinks for its addons at the repo root.

```bash
# Add a submodule, track branch 18.0, and create all addon symlinks automatically
oops-sub-add https://github.com/OCA/server-ux.git -b 18.0 --auto-symlinks

# Add a submodule and symlink only specific addons
oops-sub-add https://github.com/OCA/server-ux.git -b 18.0 --addons mass_editing,web_notify

# Preview planned actions without touching the repo
oops-sub-add https://github.com/OCA/server-ux.git -b 18.0 --auto-symlinks --dry-run
```

| Option | Description |
|--------|-------------|
| `-b, --branch` | Branch to track (e.g. `18.0`) |
| `--base-dir` | Root folder for submodules (default: `.third-party`) |
| `--name` | Override submodule name (default: `<ORG>/<REPO>`) |
| `--auto-symlinks` | Create a symlink at the repo root for every addon found |
| `--addons` | Comma-separated list of specific addons to symlink |
| `--pull-request` | Mark the submodule as a PR reference (affects naming and path) |
| `--no-commit` | Stage changes but do not commit |
| `--dry-run` | Print the plan without making any changes |

#### `oops-sub-show`
Display a table of all submodules with their upstream branch, last commit date, age, and SHA.

```bash
oops-sub-show                  # all submodules
oops-sub-show --pull-request   # pull-request submodules only
```

#### `oops-sub-check`
Check all submodules for common issues (wrong URL scheme, missing branch, deprecated repos, broken symlinks).

#### `oops-sub-fix`
Fix detected submodule issues: normalise URLs to SSH, replace deprecated repository paths.

```bash
oops-sub-fix
oops-sub-fix --no-commit
```

#### `oops-sub-update [names...]`
Fetch and update submodules to their latest upstream commit.

```bash
oops-sub-update                        # all submodules
oops-sub-update apikcloud/apik-addons  # one submodule by name
oops-sub-update --skip-pr              # skip PR submodules
oops-sub-update --dry-run
```

#### `oops-sub-prune [names...]`
Remove submodules that have no symlink pointing at them and clean up stale paths.

```bash
oops-sub-prune --dry-run   # preview what would be removed
oops-sub-prune             # remove and commit
```

#### `oops-sub-rename [names...]`
Rename submodules to match the `<ORG>/<REPO>` naming convention.

```bash
oops-sub-rename --dry-run
oops-sub-rename --no-prompt   # rename all without interactive confirmation
```

#### `oops-sub-replace <names...> <url> <branch>`
Swap one or more existing submodules for a new repository.

```bash
oops-sub-replace old-sub https://github.com/OCA/new-repo.git 18.0
oops-sub-replace sub-a sub-b https://github.com/OCA/new-repo.git 18.0 --dry-run
```

#### `oops-sub-rewrite [names...]`
Move submodule paths under a canonical base directory (default: `.third-party`) and update all symlinks.

```bash
oops-sub-rewrite --dry-run
oops-sub-rewrite --base-dir .third-party --force
```

#### `oops-sub-branch`
Detect submodules missing a `branch` entry in `.gitmodules` and set one interactively.

```bash
oops-sub-branch --branch 18.0   # default branch to suggest
oops-sub-branch --skip-pr       # ignore PR submodules
```

#### `oops-sub-clean`
Remove stale submodule directories (`.third-party`, `third-party`) and run `git submodule update`.

```bash
oops-sub-clean
oops-sub-clean --reset   # hard-reset before cleaning
```

---

### Addon commands

#### `oops-addons-list`
List all addons discovered across submodules.

```bash
oops-addons-list                      # table output
oops-addons-list --format json        # JSON (pipe-friendly)
oops-addons-list --format csv         # CSV
oops-addons-list --symlinks-only      # symlinked addons only
oops-addons-list --all                # include addons at repo root
oops-addons-list --init               # init missing submodules first
oops-addons-list -n apikcloud/apik-addons  # limit to one submodule
```

#### `oops-addons-add <addons>`
Create root-level symlinks for specific addons from any tracked submodule.

```bash
oops-addons-add mass_editing,web_notify
oops-addons-add mass_editing --no-commit
```

#### `oops-addons-diff <mode> [number]`
Find which addons changed since the last tag or in the last N commits, and print the `odoo --update` command.

```bash
oops-addons-diff tag              # since the last git tag
oops-addons-diff commit 3         # across the last 3 commits
oops-addons-diff tag --save       # also write migrate.sh
```

#### `oops-addons-materialize <addons>`
Replace a symlink with a real copy of the addon directory (for local modifications).

```bash
oops-addons-materialize my_addon
oops-addons-materialize my_addon --dry-run
oops-addons-materialize my_addon --no-commit
```

#### `oops-addons-download <url> <branch>`
Download a repository branch as a ZIP and extract addons into the working directory.

```bash
oops-addons-download https://github.com/OCA/server-ux.git 18.0
oops-addons-download https://github.com/OCA/server-ux.git 18.0 --addons mass_editing
oops-addons-download https://github.com/OCA/server-ux.git 18.0 --token $GH_TOKEN
```

The `--no-exclude` flag skips adding downloaded addons to `.gitignore`.

#### `oops-readme-update`
Generate or refresh the addon inventory table inside the repo's `README.md`. Creates `README.md` with the marker skeleton if the file does not exist. Commits automatically unless `--no-commit` is passed.

```bash
oops-readme-update            # update table and commit if changed
oops-readme-update --no-commit
```

---

### Project commands

#### `oops-pro-info`
Display a summary of the current project: Odoo version, Docker image age, available updates, git status, and (optionally) the latest GitHub Actions run.

```bash
oops-pro-info
oops-pro-info --token $GH_TOKEN   # include CI status
oops-pro-info --minimal           # shorter output
```

#### `oops-pro-check`
Validate project structure (mandatory files, image health) and print warnings or errors.

```bash
oops-pro-check
oops-pro-check --strict   # exit non-zero on warnings too
```

#### `oops-pro-update`
Update `odoo_version.txt` to the latest available Docker image for the current Odoo version.

```bash
oops-pro-update           # prompts for confirmation
oops-pro-update --force   # skip prompt
```

#### `oops-pro-exclude`
Add symlinked addons to the `.pre-commit-exclusions` file so pre-commit hooks skip them.

```bash
oops-pro-exclude
oops-pro-exclude --no-commit
```

---

## Development
1. Create and activate a virtual environment.
2. Install development dependencies: `pip install -e .[dev]` (or `make install`).
3. Run quality checks before opening a pull request:
   - `make lint` to execute Ruff.
   - `make typecheck` to run Pyright (soft-fail by design).
   - `make test` to execute the pytest suite.
4. Build artefacts locally with `make build` when you need wheels or source distributions.

## Precommit usage

You can add `oops` features in your precommit by doing the following:
```yaml
  - repo: local
    hooks:
      - id: update-readme-table
        name: Update Addons Table in README
        entry: oops-addons-table
        language: system
        pass_filenames: false
```

This way, your precommit will use your local version to execute actions on your project.

## Contributing and support
Issues and pull requests are welcome on GitHub. Please include clear reproduction steps, add tests or
changelog fragments when relevant, and describe the impact on downstream projects so reviews can move
quickly. The scripts are provided as-is by the Apik team; feel free to fork if you need bespoke behaviour.

## License
oops is distributed under the AGPL-3.0-only license. See `LICENSE` or visit
https://www.gnu.org/licenses/agpl-3.0.html for the full text.
