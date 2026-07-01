# Migrate

::: oops.commands.migrate
    options:
      show_root_heading: false
      show_docstring_modules: true

---

::: mkdocs-click:commands
    :module: oops.commands.migrate.analyze
    :command: main
    :prog_name: oops migrate analyze
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the migrate pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Snapshot with automatic version and upstream probing:

```bash
oops migrate --token $GH_TOKEN analyze
```

Offline run — skip GitHub API calls:

```bash
oops migrate --token $GH_TOKEN analyze --no-probe-upstream
```

Label the snapshot and set versions explicitly:

```bash
oops migrate --token $GH_TOKEN analyze --source-ref 18.0 --from 18.0 --to 19.0
```

Write a JSON report:

```bash
oops migrate --token $GH_TOKEN analyze --format json --output-path state_report.json
```

---

::: mkdocs-click:commands
    :module: oops.commands.migrate.plan
    :command: main
    :prog_name: oops migrate plan
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the migrate pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Seed plan.yml on first run (requires state.yml from `analyze`):

```bash
oops migrate --token $GH_TOKEN plan
```

Reconcile after editing plan.yml by hand:

```bash
oops migrate --token $GH_TOKEN plan
```

Emit JSON for downstream tooling:

```bash
oops migrate --token $GH_TOKEN plan --format json
```

---

::: mkdocs-click:commands
    :module: oops.commands.migrate.prepare
    :command: main
    :prog_name: oops migrate prepare
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the migrate pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Reset destination branch to a specific Odoo version tag and create the worktree:

```bash
oops migrate --token $GH_TOKEN prepare --destination-ref 19.0
```

Override the destination branch name:

```bash
oops migrate --token $GH_TOKEN prepare --destination-ref 19.0 --destination-branch migration/19.0
```

Re-prepare from scratch (force):

```bash
oops migrate --token $GH_TOKEN prepare --destination-ref 19.0 --force
```

---

::: mkdocs-click:commands
    :module: oops.commands.migrate.apply
    :command: main
    :prog_name: oops migrate apply
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the migrate pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Dry run — show what would happen without touching git:

```bash
oops migrate --token $GH_TOKEN apply --dry-run
```

Apply all modules:

```bash
oops migrate --token $GH_TOKEN apply
```

Apply specific modules only:

```bash
oops migrate --token $GH_TOKEN apply --only sale_extension,crm_custom
```

Port modules only (skip pull):

```bash
oops migrate --token $GH_TOKEN apply --port-only
```

Pull modules only, then fast-forward-merge onto the destination branch:

```bash
oops migrate --token $GH_TOKEN apply --pull-only --merge
```

Re-apply already-done modules:

```bash
oops migrate --token $GH_TOKEN apply --force
```
