# Contributing

Issues and pull requests are welcome on [GitHub](https://github.com/apikcloud/oops).

## Guidelines

- **Python 3.7 compatibility is required** — ensures support across most Odoo versions.
- **Check before you build** — make sure the feature doesn't already exist.
- **Keep it clean** — write clear, concise code and comment where it matters.
- **Document everything** — every new command needs a docstring and usage examples in the relevant `docs/commands/*.md` file.
- **No core changes without tests** — if tests don't exist yet, write them first.
- **Follow existing conventions** — look at current commands and match the pattern.

## Command Naming

Commands are subcommands of the root `oops` CLI, grouped by scope:

    oops <scope> <verb>

### Scopes

Each scope covers a well-defined area of responsibility:

| Scope | Responsibility |
|---|---|
| `addons` | Odoo addon lifecycle (listing, downloading, diffing…) |
| `submodules` | Git submodule management |
| `readme` | README generation and maintenance |
| `project` | Project-level metadata and configuration |

### Verbs

The verb defines the default behavior — users should be able to guess
what a command does from its name alone.

| Type | Examples | Default behavior |
|---|---|---|
| **edit** | `add`, `fix`, `update`, `prune`, `rename`… | Applies changes and commits. Use `--dry-run` to preview or `--no-commit` to skip the commit. |
| **show** | `list`, `show`, `info`, `diff`, `compare` | Read-only. No side effects. |
| **check** | `check` | Validates and reports. Exits non-zero on failure. Pairs with a matching `fix` command when one exists. |

### Rules

- A new scope requires a clear, bounded responsibility — don't create one for a single command.
- Prefer an existing verb before introducing a new one.
- `check` + `fix` always come in pairs — if you add one, add the other.
- Edit commands must support `--dry-run` and `--no-commit`.

## Setup

```bash
git clone https://github.com/apikcloud/oops.git
cd oops
uv sync --extra dev
source .venv/bin/activate
```

## Quality checks

Run these before opening a pull request:

```bash
make lint       # Ruff
make typecheck  # Pyright (soft-fail)
make test       # pytest
make cov        # pytest + coverage (80% minimum)
```

## Documentation

```bash
make install-docs
make docs-serve
```

The doc site rebuilds on file changes. After modifying a command docstring,
reinstall the package to pick up the change (`make docs-serve` does this automatically).
