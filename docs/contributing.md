# Contributing

Issues and pull requests are welcome on [GitHub](https://github.com/apikcloud/oops).

## Guidelines

- **Python 3.7 compatibility is required** — ensures support across most Odoo versions.
- **Check before you build** — make sure the feature doesn't already exist.
- **Keep it clean** — write clear, concise code and comment where it matters.
- **Document everything** — every new command needs a docstring and usage examples in the relevant `docs/commands/*.md` file.
- **No core changes without tests** — if tests don't exist yet, write them first.
- **Follow existing conventions** — look at current commands and match the pattern.

## Setup

```bash
git clone https://github.com/apikcloud/oops.git
cd oops
make install
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
