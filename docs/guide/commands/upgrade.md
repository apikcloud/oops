# Upgrade

::: oops.commands.upgrade
    options:
      show_root_heading: false
      show_docstring_modules: true

`analyze`/`plan`/`prepare`/`apply` form a four-stage pipeline for *porting* custom
addons across an Odoo version bump. `vanilla` is a separate, simpler entry
point — no `state.yml`/`plan.yml`, no per-module decisions — used as the first
step of an MdV (montée de version) project when the goal is a full return to
Odoo standard rather than porting custom code forward. It removes every
discovered addon regardless of classification (custom, OCA, or third-party),
cross-checks each one against the global Odoo KB and warns — without skipping
removal — if a module looks like a real Odoo core/enterprise module (run
`oops misc build-kb --version <from_version>` beforehand so that check has
something to check against), and writes the `upgrade-util` pip requirement
into `requirements.txt` while ensuring `git` is present in `packages.txt`
(merged in, existing entries preserved) — since installing a `git+https://...`
pip requirement needs the `git` binary in the image. A later `oops requirements
update` on the resulting branch will need that requirements line re-added if
it regenerates the file.

---

::: mkdocs-click:commands
    :module: oops.commands.upgrade.analyze
    :command: main
    :prog_name: oops upgrade analyze
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the upgrade pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Snapshot with automatic version and upstream probing:

```bash
oops upgrade --token $GH_TOKEN analyze
```

Offline run — skip GitHub API calls:

```bash
oops upgrade --token $GH_TOKEN analyze --no-probe-upstream
```

Label the snapshot and set versions explicitly:

```bash
oops upgrade --token $GH_TOKEN analyze --source-ref 18.0 --from 18.0 --to 19.0
```

Write a JSON report:

```bash
oops upgrade --token $GH_TOKEN analyze --format json --output-path state_report.json
```

---

::: mkdocs-click:commands
    :module: oops.commands.upgrade.plan
    :command: main
    :prog_name: oops upgrade plan
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the upgrade pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Seed plan.yml on first run (requires state.yml from `analyze`):

```bash
oops upgrade --token $GH_TOKEN plan
```

Reconcile after editing plan.yml by hand:

```bash
oops upgrade --token $GH_TOKEN plan
```

Emit JSON for downstream tooling:

```bash
oops upgrade --token $GH_TOKEN plan --format json
```

---

::: mkdocs-click:commands
    :module: oops.commands.upgrade.prepare
    :command: main
    :prog_name: oops upgrade prepare
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the upgrade pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Reset destination branch to a specific Odoo version tag and create the worktree:

```bash
oops upgrade prepare --destination-ref 19.0
```

Override the destination branch name:

```bash
oops upgrade prepare --destination-ref 19.0 --destination-branch upgrade/19.0
```

Re-prepare from scratch (force):

```bash
oops upgrade prepare --destination-ref 19.0 --force
```

---

::: mkdocs-click:commands
    :module: oops.commands.upgrade.apply
    :command: main
    :prog_name: oops upgrade apply
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the upgrade pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Dry run — show what would happen without touching git:

```bash
oops upgrade --token $GH_TOKEN apply --dry-run
```

Apply all modules:

```bash
oops upgrade --token $GH_TOKEN apply
```

Apply specific modules only:

```bash
oops upgrade --token $GH_TOKEN apply --only sale_extension,crm_custom
```

Port modules only (skip pull):

```bash
oops upgrade --token $GH_TOKEN apply --port-only
```

Pull modules only, then fast-forward-merge onto the destination branch:

```bash
oops upgrade --token $GH_TOKEN apply --pull-only --merge
```

Re-apply already-done modules:

```bash
oops upgrade --token $GH_TOKEN apply --force
```

---

::: mkdocs-click:commands
    :module: oops.commands.upgrade.vanilla
    :command: main
    :prog_name: oops upgrade vanilla
    :depth: 2
    :style: table

!!! warning "Experimental"
    This command is part of the upgrade pipeline. Its interface may change without
    notice between releases. The same warning is printed at runtime.

**Examples:**

Preview the removal plan without touching git:

```bash
oops upgrade vanilla --dry-run
```

Strip every non-core addon and generate the uninstall script:

```bash
oops upgrade vanilla --from 18.0
```

Override the branch and tag names:

```bash
oops upgrade vanilla --from 18.0 --branch vanilla/18.0-cleanup --tag v18-vanilla
```

Strip and generate the script without committing (review the diff by hand first):

```bash
oops upgrade vanilla --force --no-commit
```
