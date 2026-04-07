# Odoo Sources

Commands for managing local Odoo Community and Enterprise source checkouts.

All three commands share a common **base directory** that holds one subdirectory per Odoo version:

```
<sources_dir>/
├── 17.0/
│   ├── community/     ← git@github.com:odoo/odoo.git
│   └── enterprise/    ← git@github.com:odoo/enterprise.git
└── 19.0/
    └── community/
```

The base directory is configured once in `~/.oops.yaml` and shared across the team:

```yaml
odoo:
  sources_dir: ~/odoo-sources
```

All commands accept `--base-dir` to override the config value ad hoc.

---

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `odoo.sources_dir` | *(required)* | Root directory that holds version subdirectories |
| `odoo.community_url` | `git@github.com:odoo/odoo.git` | Community repository URL |
| `odoo.enterprise_url` | `git@github.com:odoo/enterprise.git` | Enterprise repository URL |

Both URL fields can be overridden to point at a fork or a mirror.

---

::: mkdocs-click:commands
    :module: oops.commands.odoo.download
    :command: main
    :prog_name: oops-odoo-download
    :depth: 2
    :style: table

**Examples:**

Clone Community and Enterprise for Odoo 19 (Enterprise is included by default):

```bash
oops-odoo-download 19.0
```

The short form `19` is also accepted and normalised to `19.0`:

```bash
oops-odoo-download 19
```

Clone Community only, skipping Enterprise:

```bash
oops-odoo-download 19.0 --no-enterprise
```

Update existing checkouts to the latest commit:

```bash
oops-odoo-download 19.0 --update
oops-odoo-download 19.0 --update --no-enterprise
```

Use a custom base directory (overrides config):

```bash
oops-odoo-download 19.0 --base-dir /tmp/odoo-src
```

---

::: mkdocs-click:commands
    :module: oops.commands.odoo.update
    :command: main
    :prog_name: oops-odoo-update
    :depth: 2
    :style: table

**Examples:**

Pull the latest commit on the branch (Enterprise included by default):

```bash
oops-odoo-update 19.0
```

Update Community only, skipping Enterprise:

```bash
oops-odoo-update 19.0 --no-enterprise
```

Checkout the state of the codebase as of a given date (detached HEAD):

```bash
oops-odoo-update 19.0 --date 2024-06-01
oops-odoo-update 19.0 --date 2024-06-01 --no-enterprise
```

!!! note
    `--date` uses a shallow fetch (`git fetch --shallow-since`). The first
    call for a given date may take a moment to download history.

---

::: mkdocs-click:commands
    :module: oops.commands.odoo.show
    :command: main
    :prog_name: oops-odoo-show
    :depth: 2
    :style: table

**Examples:**

List all locally available Odoo source checkouts:

```bash
oops-odoo-show
```

Example output:

```
| Version | Community                             | Enterprise                            |
|---------|---------------------------------------|---------------------------------------|
| 17.0    | a1b2c3d4  2024-11-15 10:22:31 +0100  | e5f6g7h8  2024-11-14 18:03:12 +0100  |
| 19.0    | 9i0j1k2l  2025-01-08 09:11:44 +0100  | —                                     |
```

A `—` in the Enterprise column means the Enterprise checkout is not present
(run `oops-odoo-download <version> --enterprise` to add it).
