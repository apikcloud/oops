# Hooks

`oops` commands are designed to be used as [pre-commit](https://pre-commit.com)
hooks. Add them to your `.pre-commit-config.yaml` under a `local` repo entry.

## Manifest

### Lint and version-bump check

Runs all manifest lint rules (author, maintainers, summary, version format,
key order) plus the version-bump check when
`manifest.version_bump_strategy` is configured.

```yaml
repos:
  - repo: local
    hooks:
      - id: oops-man-check
        name: Odoo manifest lint
        entry: oops-man-check
        language: system
        files: __manifest__\.py$
        pass_filenames: false
```

### With autofix

Prepend an `oops-man-fix` hook to apply autofixes before the check runs.
`--no-commit` prevents `oops-man-fix` from creating its own commit — the
staged changes are left for the regular commit.

```yaml
repos:
  - repo: local
    hooks:
      - id: oops-man-fix
        name: Odoo manifest autofix
        entry: oops-man-fix --no-commit
        language: system
        files: __manifest__\.py$
        pass_filenames: false

      - id: oops-man-check
        name: Odoo manifest lint
        entry: oops-man-check
        language: system
        files: __manifest__\.py$
        pass_filenames: false
```

!!! tip
    Place `oops-man-fix` **before** `oops-man-check` so autofixes are applied
    and staged before the check runs.

!!! note "Two-pass autofix"
    When both key-order and author fixes are needed on the same file, run
    `oops-man-fix` twice: the first pass reorders keys, the second applies
    the remaining fixes. See [Lint Rules](rules.md#manifestkeyorder) for details.
