# Hooks

`oops` ships a `.pre-commit-hooks.yaml` and can be used either as a
**remote repo** (pre-commit installs it automatically) or as a **local**
hook (when `oops` is already installed in the project environment).

## Remote repo

Reference the `oops` repository directly — pre-commit handles installation:

```yaml
repos:
  - repo: https://github.com/apikcloud/oops
    rev: v0.7.1  # replace with the desired release
    hooks:
      - id: check-manifest
      - id: check-submodules
      - id: check-project
```

Available hook IDs: `check-manifest`, `check-submodules`, `check-project`,
`exclude-addons`, `update-readme`.

## Local hooks

Use `language: system` when `oops` is already installed (e.g. via `uv tool`
or the project's own virtualenv):

### Manifest lint

Runs on changed manifest files only (`pass_filenames: true`).

```yaml
repos:
  - repo: local
    hooks:
      - id: oops-check-manifest
        name: Odoo manifest lint
        entry: oops-check-manifest
        language: system
        types: [python]
        files: (__manifest__\.py|__openerp__\.py)$
        pass_filenames: true
```

### With autofix

Prepend `oops-fix-manifest` to apply autofixes before the check runs.
`--no-commit` leaves the fixed files staged for the regular commit.

```yaml
repos:
  - repo: local
    hooks:
      - id: oops-fix-manifest
        name: Odoo manifest autofix
        entry: oops-fix-manifest --no-commit
        language: system
        files: (__manifest__\.py|__openerp__\.py)$
        pass_filenames: false

      - id: oops-check-manifest
        name: Odoo manifest lint
        entry: oops-check-manifest
        language: system
        types: [python]
        files: (__manifest__\.py|__openerp__\.py)$
        pass_filenames: true
```

!!! note "Two-pass autofix"
    When both key-order and author fixes are needed on the same file, run
    `oops-fix-manifest` twice: the first pass reorders keys, the second applies
    the remaining fixes. See [Lint Rules](rules.md#manifestkeyorder) for details.
